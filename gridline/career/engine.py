"""Rebuilds the whole career from the event log.

Nothing about the career is stored directly — not standings, not contracts,
not ratings. Every PC replays the same ordered events through this module and
arrives at the same state. That keeps syncing trivial (append-only log) and
means a late result or an owner's dispute ruling simply re-flows through
everything after it.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..telemetry.constants import DEFAULT_TEAM_ORDER, QUALI_TYPES, TEAMS_2026, session_kind, track_gp
from . import market, rating
from .calendar import CALENDAR_2026, DEFAULT_POINTS
from .grid import DRIVER_NAMES
from .identity import fingerprint
from .models import (
    Contract, DriverStanding, Event, Member, Offer, RatingPoint, RoundCell, SeasonState,
    SessionRecord, Submission, TeamStanding,
)

OWNER_ONLY = {"config_updated", "season_advanced", "result_resolved", "round_skipped",
              "calendar_updated", "result_voided"}

DEFAULT_CONFIG = {
    "points": DEFAULT_POINTS,
    "sprint_points": [8, 7, 6, 5, 4, 3, 2, 1],
    "fastest_lap_point": False,
    "pole_point": False,
    "track_practice": True,
    "team_order": DEFAULT_TEAM_ORDER,
    "calendar": CALENDAR_2026,
    "season_label_start": 2026,
}


@dataclass
class CareerState:
    career_id: str = ""
    name: str = ""
    seed: int = 0
    owner_id: str = ""
    config: dict = field(default_factory=lambda: dict(DEFAULT_CONFIG))
    members: dict[str, Member] = field(default_factory=dict)
    seasons: dict[int, SeasonState] = field(default_factory=dict)
    current_season: int = 1
    contracts: list[Contract] = field(default_factory=list)
    offers: dict[str, Offer] = field(default_factory=dict)
    ratings: dict[str, list[RatingPoint]] = field(default_factory=dict)
    earnings: dict[str, float] = field(default_factory=dict)
    driver_names: dict[str, str] = field(default_factory=dict)
    disputes: list[SessionRecord] = field(default_factory=list)
    log: list[tuple[float, str]] = field(default_factory=list)   # (time, text) for the activity feed

    # ---------------------------------------------------------------- helpers
    @property
    def created(self) -> bool:
        return bool(self.career_id)

    @property
    def season(self) -> SeasonState:
        return self.seasons[self.current_season]

    def season_label(self, n: int | None = None) -> str:
        n = self.current_season if n is None else n
        return str(self.config.get("season_label_start", 2026) + n - 1)

    def contract_for(self, member_id: str, season: int | None = None) -> Contract | None:
        season = self.current_season if season is None else season
        found = [c for c in self.contracts if c.member_id == member_id and c.covers(season)]
        return found[-1] if found else None

    def next_contract(self, member_id: str) -> Contract | None:
        return self.contract_for(member_id, self.current_season + 1)

    def rating_of(self, member_id: str) -> float:
        pts = self.ratings.get(member_id)
        return pts[-1].rating if pts else rating.START_RATING

    def driver_name(self, key: str) -> str:
        if key.startswith("p:"):
            m = self.members.get(key[2:])
            return m.display_name if m else "Player"
        return self.driver_names.get(key, key)

    def open_offers(self, member_id: str) -> list[Offer]:
        return [o for o in self.offers.values() if o.member_id == member_id and o.status == "open"]

    def championship_position(self, key: str, season: int | None = None) -> int | None:
        s = self.seasons.get(self.current_season if season is None else season)
        if not s:
            return None
        for i, d in enumerate(s.drivers, 1):
            if d.key == key:
                return i
        return None


# ===================================================================== helpers
def merge_qualifying(records: list[SessionRecord]) -> dict | None:
    """Combine Q1/Q2/Q3 into one grid. One-shot / short quali pass straight through."""
    if not records:
        return None
    if len(records) == 1:
        return records[0].result
    parts = sorted(records, key=lambda r: r.result.get("quali_part", 0), reverse=True)
    seen: set[str] = set()
    merged: list[dict] = []
    for rec in parts:
        for e in sorted(rec.result["entries"], key=lambda e: e["position"]):
            k = e.get("driver_key")
            if k in seen or not e.get("best_lap_ms"):
                continue
            seen.add(k)
            merged.append(dict(e))
    for rec in parts[::-1]:  # anybody with no lap at all goes to the back
        for e in rec.result["entries"]:
            if e.get("driver_key") not in seen:
                seen.add(e.get("driver_key"))
                merged.append(dict(e))
    for i, e in enumerate(merged, 1):
        e["position"] = i
    base = dict(parts[0].result)
    base["entries"] = merged
    base["session_name"] = "Qualifying"
    return base


def _reconcile(subs: list[Submission], owner_id: str, resolution: str | None) -> tuple[str, Submission]:
    # newest submission per author wins (a restarted session replaces the old one)
    latest: dict[str, Submission] = {}
    for s in sorted(subs, key=lambda s: s.created_at):
        latest[s.author] = s
    pool = list(latest.values())
    if resolution:
        for s in subs:
            if s.uid == resolution:
                return "resolved", s
    groups: dict[str, list[Submission]] = defaultdict(list)
    for s in pool:
        groups[s.fingerprint].append(s)
    agreed = [g for g in groups.values() if len({s.author for s in g}) >= 2]
    if agreed:
        return "confirmed", min(agreed[0], key=lambda s: s.created_at)
    if len(groups) == 1:
        return "provisional", min(pool, key=lambda s: s.created_at)
    owner = [s for s in pool if s.author == owner_id]
    return "disputed", owner[0] if owner else min(pool, key=lambda s: s.created_at)


# ===================================================================== engine
def build_state(events: list[Event]) -> CareerState:
    st = CareerState()
    ordered = sorted(events, key=lambda e: (e.seq is None, e.seq or 0, e.created_at))

    submissions: dict[tuple[int, int, int], list[Submission]] = defaultdict(list)
    resolutions: dict[tuple[int, int, int], str] = {}
    voided: set[str] = set()
    responses: dict[str, dict] = {}
    season_calendars: dict[int, list[int]] = {}
    skipped: dict[int, set[int]] = defaultdict(set)
    joins: list[tuple[Member, str]] = []
    seen_uids: set[str] = set()
    max_season = 1

    for ev in ordered:
        if ev.uid in seen_uids:
            continue
        seen_uids.add(ev.uid)
        p = ev.payload
        if ev.kind == "career_created":
            if st.created:
                continue
            st.career_id = ev.career_id
            st.name = p.get("name", "Career")
            st.seed = int(p.get("seed", 1))
            st.owner_id = ev.author
            st.config = {**DEFAULT_CONFIG, **p.get("config", {})}
            st.log.append((ev.created_at, f"Career “{st.name}” created"))
            continue
        if not st.created:
            continue
        if ev.kind in OWNER_ONLY and ev.author != st.owner_id:
            continue

        if ev.kind == "member_joined":
            mid = p["member_id"]
            if mid in st.members:
                continue
            m = Member(id=mid, display_name=p.get("display_name", "Driver"),
                       gamertag=p.get("gamertag", ""), is_owner=mid == st.owner_id,
                       joined_season=p.get("season", max_season))
            st.members[mid] = m
            joins.append((m, p.get("team_key", "williams")))
            st.log.append((ev.created_at, f"{m.display_name} joined the career"))
        elif ev.kind == "member_updated":
            m = st.members.get(p.get("member_id", ""))
            if m and (ev.author == m.id or ev.author == st.owner_id):
                m.display_name = p.get("display_name", m.display_name)
                m.gamertag = p.get("gamertag", m.gamertag)
        elif ev.kind == "config_updated":
            st.config.update(p.get("config", {}))
        elif ev.kind == "calendar_updated":
            season_calendars[int(p["season"])] = list(p["calendar"])
        elif ev.kind == "round_skipped":
            skipped[int(p["season"])].add(int(p["round"]))
        elif ev.kind == "season_advanced":
            to = int(p["to_season"])
            if to == max_season + 1:
                max_season = to
                if p.get("calendar"):
                    season_calendars[to] = list(p["calendar"])
                st.log.append((ev.created_at, f"Season {st.season_label(to)} started"))
        elif ev.kind == "result_submitted":
            res = p["result"]
            key = (int(p["season"]), int(p["round"]), int(res["session_type"]))
            submissions[key].append(Submission(
                uid=ev.uid, author=ev.author, created_at=ev.created_at,
                # always recompute: older app versions used a different fingerprint
                fingerprint=fingerprint(res), result=res,
                team_override=bool(p.get("team_override")),
            ))
        elif ev.kind == "result_resolved":
            resolutions[(int(p["season"]), int(p["round"]), int(p["session_type"]))] = p["submission_uid"]
        elif ev.kind == "result_voided":
            voided.add(p["submission_uid"])
        elif ev.kind == "offer_response":
            if p.get("offer", {}).get("member_id") == ev.author:
                responses.setdefault(p["offer"]["id"], p | {"_at": ev.created_at})

    if not st.created:
        return st

    st.current_season = max_season
    for m in st.members.values():
        st.ratings[m.id] = []
        st.earnings[m.id] = 0.0

    team_order = list(st.config.get("team_order") or DEFAULT_TEAM_ORDER)
    last_calendar = list(st.config.get("calendar") or CALENDAR_2026)

    for season_no in range(1, max_season + 1):
        cal = season_calendars.get(season_no, last_calendar)
        last_calendar = cal
        season = SeasonState(number=season_no, calendar=cal, skipped=skipped[season_no],
                             team_order=list(team_order))
        st.seasons[season_no] = season

        # contracts for members joining this season
        for m, team_key in joins:
            if m.joined_season == season_no and not st.contract_for(m.id, season_no):
                rank = team_order.index(team_key) if team_key in team_order else 5
                st.contracts.append(market.initial_contract(m.id, team_key, rank, season_no))

        # auto-renew anyone left without a seat
        for m in st.members.values():
            if m.joined_season <= season_no and not st.contract_for(m.id, season_no):
                prev = st.contract_for(m.id, season_no - 1)
                if prev:
                    rank = team_order.index(prev.team_key) if prev.team_key in team_order else 5
                    sal = round(min(market.team_salary_cap(rank), market.market_value(st.rating_of(m.id))), 2)
                    st.contracts.append(Contract(m.id, prev.team_key, sal, season_no, season_no,
                                                 round(sal * 0.04, 2), round(sal * 0.015, 2), "renewal"))
        # offers from the previous season that were never answered lapse now
        for o in st.offers.values():
            if o.status == "open" and o.season < season_no:
                o.status = "expired"

        # ---- sessions
        for (s_no, rnd, stype), subs in submissions.items():
            if s_no != season_no:
                continue
            subs = [s for s in subs if s.uid not in voided]
            if not subs:
                continue
            status, chosen = _reconcile(subs, st.owner_id, resolutions.get((s_no, rnd, stype)))
            kind = session_kind(stype) or "other"
            rec = SessionRecord(season_no, rnd, stype, kind, status, chosen.result, subs)
            season.sessions[(rnd, stype)] = rec
            if status == "disputed":
                st.disputes.append(rec)
            if kind in ("race", "qualifying"):
                top = min(chosen.result["entries"], key=lambda e: e["position"], default=None)
                if top:
                    who = st.driver_name(top.get("driver_key", "")) if top.get("driver_key", "").startswith("p:") \
                        else top.get("name", "")
                    what = "wins" if kind == "race" else "takes pole at"
                    if kind == "race" or stype in (7, 8, 9):
                        st.log.append((chosen.created_at, f"{who} {what} {'the ' if kind == 'race' else ''}"
                                                          f"{track_gp(cal[rnd - 1]) if rnd <= len(cal) else ''}"))
            for e in chosen.result["entries"]:
                k = e.get("driver_key", "")
                if k.startswith("ai:") or k.startswith("h:"):
                    st.driver_names.setdefault(k, e.get("name") or DRIVER_NAMES.get(e.get("driver_id"), k))

        _season_flow(st, season, team_order)
        team_order = [t.key for t in season.teams] + [k for k in team_order if k not in {t.key for t in season.teams}]
        _apply_offers_and_responses(st, season, responses)

    st.log.sort(key=lambda x: x[0])
    return st


def _expected_positions(observed: dict[str, list[int]], team_order: list[str]) -> dict[str, float]:
    exp = {}
    for i, key in enumerate(team_order):
        prior = 1.5 + 2 * i
        obs = observed.get(key, [])
        exp[key] = (prior * 3 + sum(obs)) / (3 + len(obs))
    return exp


def _season_flow(st: CareerState, season: SeasonState, team_order: list[str]) -> None:
    pts_table = list(st.config.get("points") or DEFAULT_POINTS)
    drivers: dict[str, DriverStanding] = {}
    teams: dict[str, TeamStanding] = {k: TeamStanding(k) for k in TEAMS_2026}
    observed: dict[str, list[int]] = defaultdict(list)
    n_rounds = len(season.calendar)
    season.round_expectations = {}  # type: ignore[attr-defined]

    for rnd in range(1, n_rounds + 1):
        quali_recs = [r for (rr, t), r in season.sessions.items() if rr == rnd and t in QUALI_TYPES]
        quali = merge_qualifying(quali_recs)
        race_rec = season.race(rnd)
        practice = [r.result for (rr, t), r in season.sessions.items() if rr == rnd and r.kind == "practice"]

        pole_key = None
        if quali:
            q_sorted = sorted(quali["entries"], key=lambda e: e["position"])
            if q_sorted and q_sorted[0].get("best_lap_ms"):
                pole_key = q_sorted[0].get("driver_key")
            for e in q_sorted:
                if e.get("ai") and e.get("team_key") and e.get("best_lap_ms"):
                    observed[e["team_key"]].append(e["position"])

        if race_rec:
            race = race_rec.result
            fl = race.get("fastest_lap") or {}
            fl_idx = fl.get("idx")
            for e in race["entries"]:
                if e.get("ai") and e.get("team_key") and e.get("status") == 3:
                    observed[e["team_key"]].append(e["position"])
            for e in race["entries"]:
                key = e.get("driver_key", "")
                d = drivers.get(key)
                if d is None:
                    d = drivers[key] = DriverStanding(key, st.driver_name(key), key.startswith("p:"), e.get("team_key"))
                d.team_key = e.get("team_key") or d.team_key
                classified = e.get("status") == 3 or (e.get("status") == 2 and e["position"] > 0)
                pos = e["position"]
                pts = float(pts_table[pos - 1]) if classified and pos <= len(pts_table) else 0.0
                is_fl = fl_idx is not None and e.get("idx") == fl_idx
                if is_fl and st.config.get("fastest_lap_point") and classified and pos <= 10:
                    pts += 1
                is_pole = key == pole_key
                if is_pole and st.config.get("pole_point"):
                    pts += 1
                d.points += pts
                d.cells[rnd] = RoundCell(pos if classified else None, e.get("status", 3), pts,
                                         is_pole, is_fl, e.get("team_key"))
                if classified:
                    d.finishes.append(pos)
                    d.best_finish = min(d.best_finish, pos)
                    d.wins += pos == 1
                    d.podiums += pos <= 3
                else:
                    d.dnfs += 1
                d.poles += is_pole
                d.fastest_laps += is_fl
                t = teams.get(e.get("team_key") or "")
                if t:
                    t.points += pts
                    t.cells[rnd] = t.cells.get(rnd, 0.0) + pts
                    t.wins += classified and pos == 1
                    t.podiums += classified and pos <= 3

        sprint_rec = season.sprint(rnd)
        if sprint_rec:
            sp_table = list(st.config.get("sprint_points") or [])
            for e in sprint_rec.result["entries"]:
                key = e.get("driver_key", "")
                classified = e.get("status") == 3 or (e.get("status") == 2 and e["position"] > 0)
                pos = e["position"]
                pts = float(sp_table[pos - 1]) if classified and 0 < pos <= len(sp_table) else 0.0
                if not pts:
                    continue
                d = drivers.get(key)
                if d is None:
                    d = drivers[key] = DriverStanding(key, st.driver_name(key), key.startswith("p:"), e.get("team_key"))
                d.points += pts
                if rnd in d.cells:
                    d.cells[rnd].points += pts
                else:
                    d.cells[rnd] = RoundCell(None, 0, pts, False, False, e.get("team_key"))
                t = teams.get(e.get("team_key") or "")
                if t:
                    t.points += pts
                    t.cells[rnd] = t.cells.get(rnd, 0.0) + pts

        # ratings + earnings for human drivers
        expected = _expected_positions(observed, team_order)
        season.round_expectations[rnd] = expected  # type: ignore[attr-defined]
        if race_rec or quali:
            for m in st.members.values():
                key = m.driver_key
                ent_team = None
                for res in (race_rec.result if race_rec else None, quali):
                    if res:
                        for e in res["entries"]:
                            if e.get("driver_key") == key:
                                ent_team = e.get("team_key")
                contract = st.contract_for(m.id, season.number)
                team_key = ent_team or (contract.team_key if contract else None)
                if team_key is None:
                    continue
                exp = expected.get(team_key, 11.0)
                got = rating.weekend_score(key, race_rec.result if race_rec else None, quali, practice, exp)
                if got is None:
                    continue
                score, parts = got
                prev = st.rating_of(m.id)
                st.ratings[m.id].append(RatingPoint(season.number, rnd, rating.blend(prev, score), round(score, 1), parts))
                if contract and race_rec:
                    d = drivers.get(key)
                    cell = d.cells.get(rnd) if d else None
                    earn = contract.salary / max(n_rounds, 1)
                    if cell and cell.position == 1:
                        earn += contract.win_bonus
                    if cell and cell.position and cell.position <= 3:
                        earn += contract.podium_bonus
                    st.earnings[m.id] = round(st.earnings.get(m.id, 0) + earn, 3)

    season.drivers = sorted(drivers.values(), key=lambda d: d.sort_key())
    season.teams = sorted(teams.values(), key=lambda t: (-t.points, -t.wins, team_order.index(t.key) if t.key in team_order else 99))
    if not any(t.points for t in season.teams):
        season.teams = [teams[k] for k in team_order if k in teams]
    season.final_expectations = _expected_positions(observed, team_order)  # type: ignore[attr-defined]


def _team_ranks(season: SeasonState, upto_round: int) -> dict[str, int]:
    exp = getattr(season, "round_expectations", {}).get(upto_round)
    if not exp:
        return {k: i for i, k in enumerate(season.team_order)}
    return {k: i for i, (k, _) in enumerate(sorted(exp.items(), key=lambda kv: kv[1]))}


def _apply_offers_and_responses(st: CareerState, season: SeasonState, responses: dict[str, dict]) -> None:
    n_rounds = len(season.calendar)
    done = season.rounds_done()
    windows = market.offer_windows(n_rounds)
    players_by_team: dict[str, set[str]] = defaultdict(set)
    for m in st.members.values():
        c = st.contract_for(m.id, season.number)
        if c:
            players_by_team[c.team_key].add(m.id)

    for rnd in windows:
        if rnd > done:
            break
        ranks = _team_ranks(season, rnd)
        for m in st.members.values():
            if m.joined_season > season.number:
                continue
            pts = [r for r in st.ratings.get(m.id, []) if (r.season, r.round) <= (season.number, rnd)]
            r_now = pts[-1].rating if pts else rating.START_RATING
            occupied = {t for t, ms in players_by_team.items() if ms - {m.id}}
            for o in market.generate_offers(
                st.seed, season.number, rnd, n_rounds, m.id, r_now,
                st.championship_position(m.driver_key, season.number),
                st.contract_for(m.id, season.number),
                st.next_contract(m.id) is not None and st.next_contract(m.id).start_season > season.number,
                ranks, occupied,
            ):
                st.offers.setdefault(o.id, o)

        # answer offers made in this window
        for o in list(st.offers.values()):
            if o.season != season.number or o.made_after_round != rnd:
                continue
            _apply_response(st, o, responses)

    # responses to offers that no longer regenerate (a result changed after the
    # player accepted): honour the stored copy so a signed deal never vanishes.
    for oid, resp in responses.items():
        if oid in st.offers:
            continue
        o = Offer(**{k: v for k, v in resp["offer"].items() if k in Offer.__dataclass_fields__})
        if o.season != season.number:
            continue
        st.offers[o.id] = o
        _apply_response(st, o, responses)

    for o in st.offers.values():
        if o.status == "open" and o.season == season.number and done > o.expires_after_round:
            o.status = "expired"


def _apply_response(st: CareerState, o: Offer, responses: dict[str, dict]) -> None:
    resp = responses.get(o.id)
    if not resp or o.status != "open":
        return
    if not resp.get("accept"):
        o.status = "declined"
        return
    # already committed elsewhere for next season?
    nxt = st.contract_for(o.member_id, o.season + 1)
    if nxt and nxt.start_season > o.season and nxt.source != "initial":
        o.status = "declined"
        return
    o.status = "accepted"
    # The new deal replaces whatever covered next season onwards.
    for c in st.contracts:
        if c.member_id == o.member_id and c.end_season > o.season:
            c.end_season = o.season
    # The terms the player saw and accepted are stored with the response; use them so a
    # later result change can never alter a signed deal.
    snap = resp.get("offer") or {}
    years = int(snap.get("years", o.years))
    st.contracts.append(Contract(
        member_id=o.member_id, team_key=o.team_key, salary=float(snap.get("salary", o.salary)),
        start_season=o.season + 1, end_season=o.season + years,
        win_bonus=float(snap.get("win_bonus", o.win_bonus)),
        podium_bonus=float(snap.get("podium_bonus", o.podium_bonus)),
        source="renewal" if o.kind == "renewal" else "offer",
    ))
    for other in st.offers.values():
        if other.member_id == o.member_id and other.status == "open" and other.id != o.id:
            other.status = "declined"
    m = st.members.get(o.member_id)
    who = m.display_name if m else "A driver"
    verb = "re-signed with" if o.kind == "renewal" else "signed for"
    team = TEAMS_2026.get(o.team_key, {}).get("name", o.team_key)
    st.log.append((resp.get("_at", 0), f"{who} {verb} {team} from {st.season_label(o.season + 1)}"))
