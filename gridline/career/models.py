"""Plain data structures for the career. All of it is derived from the event log."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    uid: str                 # client generated uuid, used for de-duplication
    career_id: str
    author: str              # member id
    kind: str
    payload: dict[str, Any]
    created_at: float
    seq: int | None = None   # server order; None while only local
    pending: bool = False

    def to_row(self) -> dict:
        return {
            "uid": self.uid, "career_id": self.career_id, "author": self.author,
            "kind": self.kind, "payload": self.payload, "created_at": self.created_at,
        }


@dataclass
class Member:
    id: str
    display_name: str
    gamertag: str
    is_owner: bool = False
    joined_season: int = 1

    @property
    def driver_key(self) -> str:
        return f"p:{self.id}"


@dataclass
class Contract:
    member_id: str
    team_key: str
    salary: float           # € millions per season
    start_season: int
    end_season: int         # inclusive
    win_bonus: float = 0.0
    podium_bonus: float = 0.0
    source: str = "initial"  # initial | offer | renewal

    def covers(self, season: int) -> bool:
        return self.start_season <= season <= self.end_season

    @property
    def length(self) -> int:
        return self.end_season - self.start_season + 1


@dataclass
class Offer:
    id: str
    member_id: str
    team_key: str
    salary: float
    years: int
    win_bonus: float
    podium_bonus: float
    season: int             # season the offer was made in
    made_after_round: int
    expires_after_round: int  # in `season`; season-end offers expire at next season start
    kind: str = "transfer"  # transfer | renewal
    status: str = "open"    # open | accepted | declined | expired
    interest: float = 0.0   # 0..1, how keen the team is (for display)


@dataclass
class DriverRef:
    key: str
    name: str
    is_player: bool
    member_id: str | None = None


@dataclass
class Submission:
    uid: str
    author: str
    created_at: float
    fingerprint: str
    result: dict
    team_override: bool = False


@dataclass
class SessionRecord:
    season: int
    round: int
    session_type: int
    kind: str
    status: str                      # confirmed | provisional | disputed | resolved
    result: dict                     # chosen result
    submissions: list[Submission] = field(default_factory=list)


@dataclass
class RoundCell:
    """One cell of the standings matrix."""
    position: int | None
    status: int                      # telemetry result status (3 finished, 4 DNF...)
    points: float
    pole: bool = False
    fastest_lap: bool = False
    team_key: str | None = None

    @property
    def label(self) -> str:
        if self.status in (4, 7):
            return "DNF"
        if self.status == 5:
            return "DSQ"
        if self.status == 6:
            return "NC"
        return str(self.position) if self.position else "—"


@dataclass
class DriverStanding:
    key: str
    name: str
    is_player: bool
    team_key: str | None
    points: float = 0.0
    wins: int = 0
    podiums: int = 0
    poles: int = 0
    fastest_laps: int = 0
    dnfs: int = 0
    best_finish: int = 99
    cells: dict[int, RoundCell] = field(default_factory=dict)
    finishes: list[int] = field(default_factory=list)

    def sort_key(self):
        counts = [self.finishes.count(p) for p in range(1, 23)]
        return (-self.points, *[-c for c in counts])


@dataclass
class TeamStanding:
    key: str
    points: float = 0.0
    wins: int = 0
    podiums: int = 0
    cells: dict[int, float] = field(default_factory=dict)


@dataclass
class RatingPoint:
    season: int
    round: int
    rating: float
    score: float
    parts: dict[str, float]


@dataclass
class SeasonState:
    number: int
    calendar: list[int]
    skipped: set[int] = field(default_factory=set)
    sessions: dict[tuple[int, int], SessionRecord] = field(default_factory=dict)  # (round, session_type)
    drivers: list[DriverStanding] = field(default_factory=list)
    teams: list[TeamStanding] = field(default_factory=list)
    team_order: list[str] = field(default_factory=list)   # prior strength order at season start

    def race(self, rnd: int) -> SessionRecord | None:
        """The main race of a round. On sprint weekends the game calls the sprint
        'Race' (15) and the Grand Prix 'Race 2' (16), so the highest type wins."""
        for t in (17, 16, 15):
            rec = self.sessions.get((rnd, t))
            if rec is not None:
                return rec
        return None

    def sprint(self, rnd: int) -> SessionRecord | None:
        if (rnd, 16) in self.sessions or (rnd, 17) in self.sessions:
            return self.sessions.get((rnd, 15))
        return None

    def track(self, rnd: int) -> int | None:
        return self.calendar[rnd - 1] if 1 <= rnd <= len(self.calendar) else None

    def rounds_done(self) -> int:
        return sum(1 for r in range(1, len(self.calendar) + 1) if self.race(r) or r in self.skipped)

    @property
    def complete(self) -> bool:
        return self.rounds_done() >= len(self.calendar)

    def next_round(self) -> int | None:
        for r in range(1, len(self.calendar) + 1):
            if r in self.skipped:
                continue
            if self.race(r) is None:
                return r
        return None
