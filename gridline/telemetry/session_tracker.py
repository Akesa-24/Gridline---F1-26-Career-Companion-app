"""Turns a stream of decoded packets into live timing and finished session results.

The tracker is deliberately free of Qt so it can be unit-tested and driven by
the replay/simulator tools. The listener thread feeds it packets and forwards
whatever it returns to the UI.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field

from . import constants as C
from .packets import (
    CarStatus, ClassificationEntry, EventPacket, LapEntry, Packet, Participant,
    SessionHistory, SessionInfo,
)
from .constants import PacketId


@dataclass
class _CarHistory:
    best_lap_ms: int = 0
    laps: list[int] = field(default_factory=list)       # completed valid lap times
    all_laps: list[int] = field(default_factory=list)   # completed laps incl. invalid


@dataclass
class LiveRow:
    idx: int
    position: int
    name: str
    team_key: str | None
    lap: int
    last_lap_ms: int
    best_lap_ms: int
    gap_leader_ms: int
    interval_ms: int
    tyre: str
    tyre_age: int
    pit_stops: int
    pit_status: int
    penalties_s: int
    status: int
    is_local: bool
    is_human: bool


@dataclass
class LiveSnapshot:
    session_uid: int
    session_type: int
    track_id: int
    lap: int
    total_laps: int
    time_left: int
    safety_car: int
    network_game: bool
    rows: list[LiveRow]
    fastest_lap_ms: int
    fastest_lap_idx: int | None


def _is_ai(p: Participant, idx: int, player_idx: int) -> bool:
    """AI flag, corrected for network humans whose car the AI took over after a disconnect."""
    if idx == player_idx:
        return False
    return p.ai and p.driver_id not in C.NETWORK_HUMAN_DRIVER_IDS


class SessionTracker:
    """Accumulates state for the current session.

    feed() returns a list of (kind, payload) tuples:
      ("session_started", dict)  — a new session uid appeared
      ("lobby", list[dict])      — lobby team selections changed
      ("result", dict)           — a session finished; payload is the raw result
    Live timing is pulled with snapshot() at whatever rate the UI wants.
    """

    def __init__(self) -> None:
        self.reset(0)
        self.lobby: list[dict] = []
        self.last_packet_at = 0.0
        self.format_error: int | None = None

    # ------------------------------------------------------------------ state
    def reset(self, uid: int) -> None:
        self.session_uid = uid
        self.session: SessionInfo | None = None
        self.num_active = 0
        self.participants: list[Participant] = []
        self.laps: list[LapEntry] = []
        self.status: list[CarStatus] = []
        self.history: dict[int, _CarHistory] = {}
        self.player_idx = 255
        self.fastest_lap: tuple[int, float] | None = None
        self.retirements: dict[int, int] = {}
        self.penalties: dict[int, int] = {}
        self.final: list[ClassificationEntry] | None = None
        self.final_num = 0
        self.ended = False
        self.emitted = False
        self.started_at = time.time()

    # ------------------------------------------------------------------ input
    def feed(self, pkt: Packet) -> list[tuple[str, object]]:
        out: list[tuple[str, object]] = []
        h = pkt.header
        self.last_packet_at = time.time()
        pid = h.packet_id

        if pid == PacketId.LOBBY_INFO:
            num, players = pkt.body
            lobby = [
                {"name": p.name, "team_key": C.team_key(p.team_id), "team_id": p.team_id,
                 "ai": p.ai, "ready": p.ready, "car_number": p.car_number}
                for p in players[:num]
            ]
            if lobby != self.lobby:
                self.lobby = lobby
                out.append(("lobby", lobby))
            return out

        if h.session_uid == 0:
            return out
        if h.session_uid != self.session_uid:
            self.reset(h.session_uid)
            out.append(("session_started", {"session_uid": str(h.session_uid)}))
        self.player_idx = h.player_car_index

        if pid == PacketId.SESSION:
            self.session = pkt.body
        elif pid == PacketId.PARTICIPANTS:
            self.num_active, self.participants = pkt.body
        elif pid == PacketId.LAP_DATA:
            self.laps = pkt.body
        elif pid == PacketId.CAR_STATUS:
            self.status = pkt.body
        elif pid == PacketId.SESSION_HISTORY:
            self._on_history(pkt.body)
        elif pid == PacketId.EVENT:
            res = self._on_event(pkt.body)
            if res:
                out.append(res)
        elif pid == PacketId.FINAL_CLASSIFICATION:
            num, entries = pkt.body
            if self.final is None:
                self.final, self.final_num = entries, num
            res = self._maybe_emit()
            if res:
                out.append(res)
        return out

    def _on_history(self, hist: SessionHistory) -> None:
        ch = self.history.setdefault(hist.car_idx, _CarHistory())
        completed = [lap for lap in hist.laps if lap.lap_ms > 0]
        ch.all_laps = [lap.lap_ms for lap in completed]
        ch.laps = [lap.lap_ms for lap in completed if lap.valid]
        if 0 < hist.best_lap_num <= len(hist.laps):
            ch.best_lap_ms = hist.laps[hist.best_lap_num - 1].lap_ms
        elif ch.laps:
            ch.best_lap_ms = min(ch.laps)

    def _on_event(self, ev: EventPacket):
        if ev.code == "FTLP" and ev.vehicle_idx is not None:
            self.fastest_lap = (ev.vehicle_idx, ev.lap_time_s or 0.0)
        elif ev.code == "RTMT" and ev.vehicle_idx is not None:
            self.retirements[ev.vehicle_idx] = ev.reason or 0
        elif ev.code == "PENA" and ev.vehicle_idx is not None and ev.reason in C.REAL_PENALTY_TYPES:
            self.penalties[ev.vehicle_idx] = self.penalties.get(ev.vehicle_idx, 0) + 1
        elif ev.code == "SEND":
            self.ended = True
            return self._maybe_emit(force=True)
        return None

    # ------------------------------------------------------------------ output
    def _maybe_emit(self, force: bool = False):
        if self.emitted or self.session is None or not self.participants:
            return None
        kind = C.session_kind(self.session.session_type)
        if kind is None:
            return None
        # Races need the official classification; practice and qualifying can
        # fall back to lap history if the session is ended without one.
        if self.final is None and (kind == "race" or not force):
            return None
        result = self.build_result()
        if not result["entries"]:
            return None
        self.emitted = True
        return ("result", result)

    def _car_name(self, idx: int) -> str:
        if idx < len(self.participants):
            return self.participants[idx].name or f"Car {idx + 1}"
        return f"Car {idx + 1}"

    def build_result(self) -> dict:
        s = self.session
        assert s is not None
        kind = C.session_kind(s.session_type)
        # Loop over every slot rather than num_active: online lobbies can leave gaps
        # in the car indices when somebody leaves. Empty slots are filtered below.
        entries = []
        for idx in range(len(self.participants)):
            p = self.participants[idx]
            hist = self.history.get(idx, _CarHistory())
            lap = self.laps[idx] if idx < len(self.laps) else None
            fc = self.final[idx] if self.final is not None and idx < len(self.final) else None
            if fc is not None and fc.result_status in (0, 1) and fc.position == 0:
                continue
            if fc is None and lap is not None and lap.result_status in (0, 1):
                continue

            best = (fc.best_lap_ms if fc and fc.best_lap_ms else 0) or hist.best_lap_ms
            ai = _is_ai(p, idx, self.player_idx)
            e = {
                "idx": idx,
                "name": p.name,
                "ai": ai,
                "driver_id": p.driver_id,
                "network_id": p.network_id,
                "team_id": p.team_id,
                "team_key": C.team_key(p.team_id),
                "race_number": p.race_number,
                "is_local": idx == self.player_idx,
                "best_lap_ms": best,
                "laps_completed": len(hist.all_laps),
                "penalty_count": self.penalties.get(idx, 0),
            }
            if fc is not None:
                e.update({
                    "position": fc.position,
                    "grid": fc.grid,
                    "laps": fc.laps,
                    "pit_stops": fc.pit_stops,
                    "status": fc.result_status,
                    "reason": fc.result_reason,
                    "total_time_s": round(fc.total_time_s, 3),
                    "penalties_s": fc.penalties_s,
                    "penalty_count": fc.num_penalties,
                    "tyres": [C.VISUAL_TYRES.get(t, "?") for t in fc.stints_visual],
                })
            else:
                e.update({
                    "position": 0,
                    "grid": lap.grid_position if lap else 0,
                    "laps": len(hist.all_laps),
                    "pit_stops": lap.pit_stops if lap else 0,
                    "status": 3,
                    "reason": 2,
                    "total_time_s": 0.0,
                    "penalties_s": lap.penalties_s if lap else 0,
                    "tyres": [],
                })
            if not ai:
                laps = hist.laps
                e["lap_times_ms"] = laps
                e["lap_stdev_ms"] = int(statistics.pstdev(laps)) if len(laps) >= 3 else None
            entries.append(e)

        # Practice / qualifying without a classification: order by best lap.
        if all(e["position"] == 0 for e in entries):
            timed = sorted(entries, key=lambda e: (e["best_lap_ms"] == 0, e["best_lap_ms"]))
            for pos, e in enumerate(timed, 1):
                e["position"] = pos
        entries.sort(key=lambda e: e["position"])

        fastest = None
        timed = [e for e in entries if e["best_lap_ms"] > 0]
        if timed:
            f = min(timed, key=lambda e: e["best_lap_ms"])
            fastest = {"idx": f["idx"], "best_lap_ms": f["best_lap_ms"]}

        return {
            "session_uid": str(self.session_uid),
            "session_type": s.session_type,
            "session_name": C.SESSION_TYPES.get(s.session_type, "Session"),
            "kind": kind,
            "quali_part": C.QUALI_PART.get(s.session_type, 0),
            "track_id": s.track_id,
            "total_laps": s.total_laps,
            "network_game": s.network_game,
            "ai_difficulty": s.ai_difficulty,
            "weekend_link": s.weekend_link,
            "player_idx": self.player_idx,
            "fastest_lap": fastest,
            "entries": entries,
            "captured_at": time.time(),
        }

    def snapshot(self) -> LiveSnapshot | None:
        s = self.session
        if s is None or not self.participants or not self.laps:
            return None
        rows: list[LiveRow] = []
        for idx in range(min(len(self.participants), len(self.laps))):
            lap = self.laps[idx]
            if lap.result_status in (0, 1):
                continue
            p = self.participants[idx]
            st = self.status[idx] if idx < len(self.status) else None
            hist = self.history.get(idx)
            rows.append(LiveRow(
                idx=idx, position=lap.position, name=p.name, team_key=C.team_key(p.team_id),
                lap=lap.current_lap, last_lap_ms=lap.last_lap_ms,
                best_lap_ms=hist.best_lap_ms if hist else 0,
                gap_leader_ms=lap.delta_leader_ms, interval_ms=lap.delta_front_ms,
                tyre=C.VISUAL_TYRES.get(st.visual_tyre, "") if st else "",
                tyre_age=st.tyre_age if st else 0,
                pit_stops=lap.pit_stops, pit_status=lap.pit_status,
                penalties_s=lap.penalties_s, status=lap.result_status,
                is_local=idx == self.player_idx, is_human=not _is_ai(p, idx, self.player_idx),
            ))
        rows.sort(key=lambda r: r.position or 99)
        leader_lap = max((r.lap for r in rows), default=0)
        best = [(r.best_lap_ms, r.idx) for r in rows if r.best_lap_ms > 0]
        fl_ms, fl_idx = min(best) if best else (0, None)
        return LiveSnapshot(
            session_uid=self.session_uid, session_type=s.session_type, track_id=s.track_id,
            lap=leader_lap, total_laps=s.total_laps, time_left=s.time_left,
            safety_car=s.safety_car_status, network_game=s.network_game,
            rows=rows, fastest_lap_ms=fl_ms, fastest_lap_idx=fl_idx,
        )
