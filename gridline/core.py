"""Application core: glues the store, career engine, telemetry and sync together.

The UI only talks to this object. It owns the active career, rebuilds the
career state whenever the event log changes and decides what happens to a
captured session.
"""
from __future__ import annotations

import json
import random
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .career import market
from .career.engine import CareerState, build_state
from .career.identity import assign_driver_keys, fingerprint, strip_for_upload
from .career.models import Member, Offer
from .sync import invite
from .sync.store import Store, data_dir
from .sync.supabase import SupabaseBackend, normalise_url
from .sync.worker import SyncWorker
from .telemetry import constants as C
from .telemetry.listener import TelemetryListener

RECENT_SLOT_WINDOW = 6 * 3600
WEEKEND_WINDOW = 12 * 3600


@dataclass
class PendingCapture:
    id: str
    result: dict
    season: int
    round: int
    warnings: list[str] = field(default_factory=list)
    team_mismatch: bool = False
    track_mismatch: bool = False


class AppCore(QObject):
    state_changed = Signal(object)          # CareerState
    careers_changed = Signal()
    live = Signal(object)                   # LiveSnapshot
    lobby = Signal(object)
    telemetry_state = Signal(str, str)      # state, message
    sync_state = Signal(str, str)
    capture_needs_review = Signal(object)   # PendingCapture
    toast = Signal(str, str)                # level (info|ok|warn|error), text

    def __init__(self, store: Store | None = None):
        super().__init__()
        self.store = store or Store()
        self.state = CareerState()
        self.career: dict | None = None
        self.listener: TelemetryListener | None = None
        self.sync: SyncWorker | None = None
        self.pending_captures: dict[str, PendingCapture] = {}
        self.telemetry = ("idle", "Telemetry off")
        self.sync_status = ("local", "")
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(60)
        self._rebuild_timer.timeout.connect(self.rebuild)
        self._retired: list = []        # threads that were asked to stop but are still finishing
        self._last_pending = -1

    # ================================================================ lifecycle
    def start(self) -> None:
        active = self.store.get("active_career")
        careers = self.store.careers()
        if careers:
            ids = [c["id"] for c in careers]
            self.open_career(active if active in ids else ids[0])
        self.start_telemetry()

    def shutdown(self) -> None:
        threads = [t for t in (self.listener, self.sync) if t] + self._retired
        for t in threads:
            t.request_stop()
        for t in threads:
            # a sync request can be mid-flight; give it its full timeout, then give up
            if not t.wait(9000):
                t.terminate()
                t.wait(1000)
        self.listener = self.sync = None
        self._retired.clear()

    def _retire(self, thread) -> None:
        """Stop a QThread without destroying it while it still runs (which aborts the app)."""
        thread.request_stop()
        if thread.wait(300):
            return
        self._retired.append(thread)
        thread.finished.connect(lambda t=thread: self._retired.remove(t) if t in self._retired else None)

    # ================================================================ telemetry
    @property
    def udp_port(self) -> int:
        return int(self.store.get("udp_port", 20777))

    def start_telemetry(self) -> None:
        if self.listener:
            self._retire(self.listener)
            self.listener = None
        rec = None
        if self.store.get("record_packets", False):
            rec = data_dir() / "captures" / time.strftime("session-%Y%m%d-%H%M%S.gridcap")
            rec.parent.mkdir(exist_ok=True)
        self.listener = TelemetryListener(port=self.udp_port, record_to=rec)
        self.listener.snapshot.connect(self.live)
        self.listener.lobby.connect(self.lobby)
        self.listener.result.connect(self.on_session_result)
        # bound methods (not lambdas) so these run queued on the GUI thread
        self.listener.state.connect(self._on_tel_state)
        self.listener.message.connect(self._on_tel_message)
        self.listener.start()

    def _on_tel_state(self, state: str) -> None:
        self._set_telemetry(state, None)

    def _on_tel_message(self, msg: str) -> None:
        self._set_telemetry(None, msg)

    def _set_telemetry(self, state: str | None, msg: str | None) -> None:
        s, m = self.telemetry
        self.telemetry = (state or s, msg or m)
        self.telemetry_state.emit(*self.telemetry)

    def set_udp_port(self, port: int) -> None:
        self.store.set("udp_port", int(port))
        self.start_telemetry()

    # ================================================================ careers
    @property
    def me(self) -> str:
        return self.career["member_id"] if self.career else ""

    @property
    def is_owner(self) -> bool:
        return bool(self.career) and self.state.owner_id == self.me

    @property
    def is_local_only(self) -> bool:
        return not self.career or self.career["backend"].get("type") != "supabase"

    def careers(self) -> list[dict]:
        return self.store.careers()

    def open_career(self, career_id: str) -> None:
        if self.sync:
            self._retire(self.sync)
            self.sync = None
        self.career = self.store.career(career_id)
        if not self.career:
            return
        self.store.set("active_career", career_id)
        self.sync = SyncWorker(self.store, self.career)
        self.sync.changed.connect(self._rebuild_timer.start)
        self.sync.status.connect(self._on_sync_status)
        self.sync.start()
        self.rebuild()
        self.careers_changed.emit()
        QTimer.singleShot(800, self._restore_pending_captures)

    def _on_sync_status(self, state: str, detail: str) -> None:
        changed = (state, detail) != self.sync_status
        self.sync_status = (state, detail)
        if changed:
            self.sync_state.emit(state, detail)
        # Only rebuild when uploads finished (pending markers changed) — rebuilding on
        # every poll would reset half-edited settings and views every few seconds.
        n = self.pending_count()
        if n != self._last_pending:
            self._last_pending = n
            self.sync_state.emit(state, detail)
            self._rebuild_timer.start()

    def rebuild(self) -> None:
        if not self.career:
            self.state = CareerState()
        else:
            self.state = build_state(self.store.events(self.career["id"]))
            if self.state.created and self.state.name != self.career["name"]:
                self.store.rename_career(self.career["id"], self.state.name)
                self.career["name"] = self.state.name
        self.state_changed.emit(self.state)

    def pending_count(self) -> int:
        return len(self.store.pending(self.career["id"])) if self.career else 0

    def _emit(self, kind: str, payload: dict) -> None:
        assert self.career
        self.store.new_event(self.career["id"], self.me, kind, payload, local_only=self.is_local_only)
        self.rebuild()
        if self.sync:
            self.sync.poke()

    @staticmethod
    def prepare_remote_career(backend: dict, name: str) -> str:
        """Network part of creating a career. Safe to run on a worker thread."""
        career_id = str(uuid.uuid4())
        if backend.get("type") == "supabase":
            be = SupabaseBackend(backend["url"], backend["key"])
            be.check()
            be.create_career(career_id, name)
        return career_id

    def create_career(self, name: str, display_name: str, gamertag: str, team_key: str,
                      backend: dict, config: dict | None = None, career_id: str | None = None) -> str:
        """Local part of creating a career (GUI thread). Call prepare_remote_career first
        for shared careers; without a career_id this does the network step inline."""
        if career_id is None:
            career_id = self.prepare_remote_career(backend, name)
        member_id = uuid.uuid4().hex[:12]
        if backend.get("type") == "supabase":
            backend = dict(backend, url=normalise_url(backend["url"]))
        self.store.add_career(career_id, name, member_id, backend)
        local = backend.get("type") != "supabase"
        self.store.new_event(career_id, member_id, "career_created",
                             {"name": name, "seed": random.randint(1, 2**31), "config": config or {}}, local)
        self.store.new_event(career_id, member_id, "member_joined",
                             {"member_id": member_id, "display_name": display_name,
                              "gamertag": gamertag, "team_key": team_key, "season": 1}, local)
        self.open_career(career_id)
        return career_id

    def preview_invite(self, code: str) -> dict:
        """Network part of joining: fetch the whole career log. Safe on a worker thread."""
        info = invite.decode(code)
        be = SupabaseBackend(info["url"], info["key"])
        be.check()
        name = be.career_exists(info["career_id"])
        if name is None:
            raise invite.InvalidInvite("That career no longer exists on the owner's database")
        info["name"] = name
        rows, last = [], 0
        while True:
            page = be.pull(info["career_id"], last)
            rows += page
            if len(page) < 500:
                break
            last = page[-1]["seq"]
        info["rows"] = rows
        info["state"] = build_state([_row_event(info["career_id"], r) for r in rows])
        info["already_here"] = self.store.career(info["career_id"]) is not None
        return info

    @staticmethod
    def find_existing_member(st: CareerState, display_name: str, gamertag: str) -> Member | None:
        """A member with the same in-game name (or display name) — used to rejoin as yourself."""
        def norm(x):
            return re.sub(r"\W", "", (x or "").casefold())
        for m in st.members.values():
            if gamertag and norm(m.gamertag) == norm(gamertag):
                return m
        for m in st.members.values():
            if display_name and norm(m.display_name) == norm(display_name):
                return m
        return None

    def join_career(self, info: dict, display_name: str, gamertag: str, team_key: str,
                    reclaim: Member | None = None) -> None:
        """Local part of joining (GUI thread), using the rows preview_invite fetched.

        If `reclaim` is given the player takes back an existing driver (for example after
        leaving and rejoining), keeping their results, contracts and owner rights.
        """
        cid = info["career_id"]
        if self.store.career(cid) is not None:
            raise invite.InvalidInvite("This career is already on this PC — switch to it in Settings › Careers.")
        member_id = reclaim.id if reclaim else uuid.uuid4().hex[:12]
        url = normalise_url(info["url"])
        self.store.add_career(cid, info["name"], member_id, {"type": "supabase", "url": url, "key": info["key"]})
        self.store.merge_remote(cid, info.get("rows", []))
        if reclaim is None:
            st = info["state"]
            self.store.new_event(cid, member_id, "member_joined",
                                 {"member_id": member_id, "display_name": display_name, "gamertag": gamertag,
                                  "team_key": team_key, "season": st.current_season if st.created else 1}, False)
        self.open_career(cid)

    def invite_code(self) -> str | None:
        if not self.career or self.is_local_only:
            return None
        b = self.career["backend"]
        return invite.encode(b["url"], b["key"], self.career["id"], self.state.name or self.career["name"])

    def leave_career(self) -> None:
        if not self.career:
            return
        cid = self.career["id"]
        if self.sync:
            self._retire(self.sync)
            self.sync = None
        self.store.remove_career(cid)
        self.store.set(f"pending_captures:{cid}", None)
        self.career = None
        rest = self.store.careers()
        if rest:
            self.open_career(rest[0]["id"])
        else:
            self.store.set("active_career", None)
            self.rebuild()
            self.careers_changed.emit()

    def export_career(self, path: Path) -> None:
        assert self.career
        events = [e.to_row() | {"seq": e.seq} for e in self.store.events(self.career["id"])]
        path.write_text(json.dumps({"career": self.career["name"], "events": events}, indent=1), encoding="utf-8")

    # ================================================================ commands
    def respond_offer(self, offer: Offer, accept: bool) -> None:
        self._emit("offer_response", {"offer": offer.__dict__, "accept": accept})
        team = C.team_name(offer.team_key)
        self.toast.emit("ok" if accept else "info",
                        f"Signed with {team} from {self.state.season_label(offer.season + 1)}" if accept
                        else f"Declined {team}")

    def resolve_dispute(self, season: int, rnd: int, session_type: int, submission_uid: str) -> None:
        self._emit("result_resolved", {"season": season, "round": rnd, "session_type": session_type,
                                       "submission_uid": submission_uid})

    def void_submission(self, submission_uid: str) -> None:
        self._emit("result_voided", {"submission_uid": submission_uid})

    def advance_season(self, calendar: list[int] | None = None) -> None:
        self._emit("season_advanced", {"to_season": self.state.current_season + 1,
                                       "calendar": calendar or self.state.season.calendar})

    def skip_round(self, rnd: int) -> None:
        self._emit("round_skipped", {"season": self.state.current_season, "round": rnd})

    def update_config(self, patch: dict) -> None:
        self._emit("config_updated", {"config": patch})

    def update_calendar(self, calendar: list[int]) -> None:
        self._emit("calendar_updated", {"season": self.state.current_season, "calendar": calendar})

    def update_profile(self, display_name: str, gamertag: str) -> None:
        self._emit("member_updated", {"member_id": self.me, "display_name": display_name, "gamertag": gamertag})

    # ================================================================ capture
    def on_session_result(self, raw: dict) -> None:
        if not self.career or not self.state.created:
            self.toast.emit("warn", f"{raw['session_name']} finished, but no career is open — result not saved")
            return
        st = self.state
        if raw["kind"] == "practice" and not st.config.get("track_practice", True):
            return
        if self.me not in st.members:
            self.toast.emit("warn", "You are not a member of this career yet")
            return
        result = assign_driver_keys(raw, st.members, self.me)
        season = st.season
        rnd = self._round_for(result)
        if rnd is None:
            self.toast.emit("warn", "The season is complete. Start the next season to keep recording results.")
            return

        cap = PendingCapture(id=uuid.uuid4().hex, result=result, season=season.number, round=rnd)
        planned = season.track(rnd)
        if planned is not None and result["track_id"] != planned:
            cap.track_mismatch = True
            cap.warnings.append(
                f"This session was at {C.track_name(result['track_id'])}, but round {rnd} is "
                f"{C.track_gp(planned)} ({C.track_name(planned)})."
            )
        mine = next((e for e in result["entries"] if e.get("driver_key") == f"p:{self.me}"), None)
        contract = st.contract_for(self.me)
        if mine is None:
            cap.warnings.append("Your car wasn't found in the classification (spectating?).")
        elif contract and mine.get("team_key") != contract.team_key:
            cap.team_mismatch = True
            cap.warnings.append(
                f"You drove the {C.team_name(mine.get('team_key'))}, but your contract is with "
                f"{C.team_name(contract.team_key)}."
            )
        if cap.warnings:
            self.pending_captures[cap.id] = cap
            self._save_pending()
            self.capture_needs_review.emit(cap)
            return
        self.commit_capture(cap)

    # Results waiting for the player's decision survive an app or PC restart.
    def _save_pending(self) -> None:
        if self.career:
            self.store.set(f"pending_captures:{self.career['id']}",
                           [asdict(c) for c in self.pending_captures.values()])

    def _restore_pending_captures(self) -> None:
        if not self.career:
            return
        saved = self.store.get(f"pending_captures:{self.career['id']}") or []
        for d in saved:
            if d["id"] not in self.pending_captures:
                cap = PendingCapture(**d)
                self.pending_captures[cap.id] = cap
                self.capture_needs_review.emit(cap)

    def _round_for(self, result: dict) -> int | None:
        """Pick the round a session belongs to.

        Normally the next round without a race. But if the other player's copy
        of this very session already synced (possibly including the race that
        advanced the round), attach to that slot instead.
        """
        season = self.state.season
        fp = fingerprint(result)
        now = time.time()
        track = result.get("track_id")
        stype_new = result["session_type"]
        # 1) this very session (other PC's copy) or same session type just captured by the other PC
        for (rnd, stype), rec in season.sessions.items():
            if stype != result["session_type"]:
                continue
            if any(s.fingerprint == fp for s in rec.submissions):
                return rnd
            mine = any(s.author == self.me for s in rec.submissions)
            recent = max(s.created_at for s in rec.submissions) > now - RECENT_SLOT_WINDOW
            if not mine and recent and rec.result.get("track_id") == track:
                return rnd
        # 2) same race weekend according to the game (weekend link persists across sessions)
        link = result.get("weekend_link") or 0
        if link:
            for (rnd, _t), rec in sorted(season.sessions.items(), reverse=True):
                if (rec.result.get("weekend_link") == link and rec.result.get("track_id") == track
                        and max(s.created_at for s in rec.submissions) > now - WEEKEND_WINDOW):
                    return rnd
        # 3) sprint weekend: the sprint was recorded as 'Race' and closed the round, but the
        #    Grand Prix, qualifying etc. at the same track still belong to it
        if stype_new != 15:
            for rnd in range(len(season.calendar), 0, -1):
                sprint_only = (rnd, 15) in season.sessions and (rnd, 16) not in season.sessions
                if not sprint_only:
                    continue
                rec = season.sessions[(rnd, 15)]
                if rec.result.get("track_id") == track and \
                        max(s.created_at for s in rec.submissions) > now - WEEKEND_WINDOW and \
                        (stype_new in (16, 17) or season.next_round() != rnd):
                    return rnd
                break
        return season.next_round()

    def commit_capture(self, cap: PendingCapture) -> None:
        self.pending_captures.pop(cap.id, None)
        self._save_pending()
        payload = {
            "season": cap.season, "round": cap.round,
            "result": strip_for_upload(cap.result), "fingerprint": fingerprint(cap.result),
            "team_override": cap.team_mismatch,
        }
        self._emit("result_submitted", payload)
        self.toast.emit("ok", f"{cap.result['session_name']} saved to round {cap.round} — "
                              f"{C.track_gp(self.state.season.track(cap.round))}")

    def discard_capture(self, cap: PendingCapture) -> None:
        self.pending_captures.pop(cap.id, None)
        self._save_pending()
        self.toast.emit("info", f"{cap.result['session_name']} discarded")

    # ================================================================ queries
    def member_contract_value(self, member_id: str) -> float:
        return market.market_value(self.state.rating_of(member_id),
                                   self.state.championship_position(f"p:{member_id}"))

    def my_member(self) -> Member | None:
        return self.state.members.get(self.me)


def _row_event(career_id: str, r: dict):
    from .career.models import Event
    return Event(uid=str(r["uid"]), career_id=career_id, author=r["author"], kind=r["kind"],
                 payload=r["payload"], created_at=r["created_at"], seq=r["seq"])
