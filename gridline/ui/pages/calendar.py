"""Calendar — every round of the season, and the full classification of each session."""
from __future__ import annotations


from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from ...career.engine import CareerState, merge_qualifying
from ...telemetry import constants as C
from ..theme import P, font
from ..widgets.common import (
    Card, Chip, EmptyState, Segmented, button, clear_layout, fmt_gap, fmt_lap, fmt_race_time, label,
)
from ..widgets.table import DataTable
from .base import Page

STATUS_CHIP = {"confirmed": ("Confirmed by both PCs", "ok"), "provisional": ("Provisional — one PC so far", "warn"),
               "disputed": ("Disputed — owner to rule", "bad"), "resolved": ("Ruled by owner", "accent")}


class CalendarPage(Page):
    title = "Calendar"

    def __init__(self, core):
        super().__init__(core)
        self.selected_round = None
        row = QHBoxLayout()
        row.setSpacing(18)

        left = Card(padding=10)
        self.rounds = DataTable([("RD", 46), ("GRAND PRIX", None), ("WINNER", 150), ("", 104)],
                                row_height=44, selectable=True)
        self.rounds.cellClicked.connect(self._pick)
        left.add(self.rounds)
        left.setMinimumWidth(470)
        row.addWidget(left, 5)

        self.detail = Card(padding=20, spacing=12)
        top = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(0)
        self.d_round = label("", "section")
        self.d_title = label("")
        self.d_title.setFont(font(19, QFont.Weight.Bold))
        self.d_track = label("", "muted")
        col.addWidget(self.d_round)
        col.addWidget(self.d_title)
        col.addWidget(self.d_track)
        top.addLayout(col, 1)
        self.skip_btn = button("Skip round", "ghost")
        self.skip_btn.clicked.connect(self._skip)
        top.addWidget(self.skip_btn)
        self.detail.add(top)
        tabs_row = QHBoxLayout()
        self.tabs = Segmented(["Race", "Qualifying", "Practice"])
        self.tabs.changed.connect(lambda _: self._render_detail())
        tabs_row.addWidget(self.tabs)
        tabs_row.addStretch(1)
        self.rec_chip = Chip("", "ok")
        tabs_row.addWidget(self.rec_chip)
        self.detail.add(tabs_row)
        self.detail_body = QVBoxLayout()
        self.detail_body.setSpacing(8)
        self.detail.add(self.detail_body, 1)
        self.detail.v.addStretch(1)
        row.addWidget(self.detail, 7)
        self.body.addLayout(row, 1)

    def _pick(self, r: int, _c: int) -> None:
        self.selected_round = self.rounds.payload(r)
        self._render_detail()

    def _skip(self) -> None:
        st = self.core.state
        rnd = self.selected_round
        if rnd is None:
            return
        gp = C.track_gp(st.season.track(rnd))
        if QMessageBox.question(self, "Skip round", f"Skip round {rnd} ({gp}) for everyone? "
                                "No points are awarded and the career moves on.") == QMessageBox.StandardButton.Yes:
            self.core.skip_round(rnd)

    def refresh(self, st: CareerState) -> None:
        if not st.created:
            return
        season = st.season
        self.header.set_subtitle(f"Season {st.season_label()}  ·  {len(season.calendar)} rounds")
        nxt = season.next_round()
        if self.selected_round is None or self.selected_round > len(season.calendar):
            self.selected_round = nxt or len(season.calendar)
        rows, hl, payloads = [], [], []
        for i, tid in enumerate(season.calendar, 1):
            race = season.race(i)
            winner = ""
            if race:
                w = min(race.result["entries"], key=lambda e: e["position"])
                winner = st.driver_name(w.get("driver_key", "")) if w.get("driver_key", "").startswith("p:") else w["name"]
                status = ("Done", {"badge": "DONE", "badge_colours": (P.ok, "#0E2E25")})
                if race.status == "disputed":
                    status = ("", {"badge": "DISPUTED", "badge_colours": (P.bad, "#35131E")})
                elif race.status == "provisional":
                    status = ("", {"badge": "PROVISIONAL", "badge_colours": (P.warn, "#33270F")})
            elif i in season.skipped:
                status = ("", {"badge": "SKIPPED", "badge_colours": (P.text2, P.card3)})
            elif i == nxt:
                status = ("", {"badge": "NEXT", "badge_colours": (P.accent2, P.accent_dim)})
            else:
                status = ("", {})
            rows.append([
                (str(i), {"fg": P.text3, "bold": True, "align": "c"}),
                (C.track_gp(tid), {"bold": i == nxt, "sub": C.track_name(tid)}),
                (winner, {"fg": P.text2}),
                ("", status[1]),
            ])
            hl.append(P.card2 if i == self.selected_round else None)
            payloads.append(i)
        self.rounds.set_rows(rows, hl, payloads)
        self.rounds.fit_height()
        self._render_detail()

    def _render_detail(self) -> None:
        st = self.core.state
        if not st.created or self.selected_round is None:
            return
        season = st.season
        rnd = self.selected_round
        tid = season.track(rnd)
        self.d_round.setText(f"ROUND {rnd}")
        self.d_title.setText(C.track_gp(tid))
        self.d_track.setText(C.track_name(tid))
        self.skip_btn.setVisible(self.core.is_owner and rnd == season.next_round())
        clear_layout(self.detail_body)

        kind = ["race", "qualifying", "practice"][self.tabs.index()]
        recs = [r for (rr, t), r in sorted(season.sessions.items()) if rr == rnd and r.kind == kind]
        if not recs:
            self.rec_chip.hide()
            self.detail_body.addWidget(EmptyState(
                f"No {kind} recorded",
                "It will appear here automatically once the session ends in the game." if rnd >= (season.next_round() or 99)
                else "This session wasn't captured for this round.", "flag"))
            return
        status_order = ["disputed", "provisional", "resolved", "confirmed"]
        worst = min((r.status for r in recs), key=status_order.index)
        t, s = STATUS_CHIP[worst]
        self.rec_chip.setText(t)
        self.rec_chip.set_style(s)
        self.rec_chip.show()

        players = {m.driver_key for m in st.members.values()}
        if kind == "qualifying":
            results = [("Qualifying", merge_qualifying(recs))]
        else:
            results = [(r.result.get("session_name", kind.title()), r.result) for r in recs]
        for title, res in results:
            if len(results) > 1:
                self.detail_body.addWidget(label(title.upper(), "section"))
            self.detail_body.addWidget(self._table(kind, res, players, st))
        subs = sorted({(s.author, s.created_at) for r in recs for s in r.submissions}, key=lambda x: x[1])
        who = ", ".join(st.members[a].display_name if a in st.members else "Unknown" for a, _ in subs)
        self.detail_body.addWidget(label(f"Captured by {who}", "faint"))

    def _table(self, kind: str, res: dict, players: set, st: CareerState) -> QWidget:
        entries = sorted(res["entries"], key=lambda e: e["position"])
        fl_idx = (res.get("fastest_lap") or {}).get("idx")
        best = min((e["best_lap_ms"] for e in entries if e.get("best_lap_ms")), default=0)
        if kind == "race":
            cols = [("POS", 46), ("DRIVER", None), ("GRID", 50), ("TIME / GAP", 120), ("BEST", 92), ("TYRES", 90), ("PIT", 40)]
        else:
            cols = [("POS", 46), ("DRIVER", None), ("BEST LAP", 100), ("GAP", 90), ("LAPS", 50)]
        t = DataTable(cols, row_height=32)
        rows, hl = [], []
        leader_time = (entries[0].get("total_time_s", 0) + entries[0].get("penalties_s", 0)) if entries else 0
        for e in entries:
            key = e.get("driver_key", "")
            name = st.driver_name(key) if key.startswith("p:") else e.get("name", "")
            dnf = e.get("status") in (4, 5, 6, 7)
            name_st = {"team": e.get("team_key"), "bold": key in players}
            if kind == "race":
                if dnf:
                    gap = C.RESULT_STATUS.get(e.get("status"), "DNF")
                elif e["position"] == 1:
                    gap = fmt_race_time(e.get("total_time_s", 0))
                else:
                    laps_down = (entries[0].get("laps", 0) - e.get("laps", 0))
                    gap = f"+{laps_down} lap{'s' if laps_down > 1 else ''}" if laps_down > 0 else \
                        f"+{e.get('total_time_s', 0) + e.get('penalties_s', 0) - leader_time:.3f}"
                rows.append([
                    ("", {"pos": e["position"] if not dnf else 0}),
                    (name, name_st),
                    (str(e.get("grid") or "—"), {"fg": P.text2, "align": "c"}),
                    (gap, {"mono": True, "fg": P.bad if dnf else P.text}),
                    (fmt_lap(e.get("best_lap_ms")), {"mono": True, "fg": P.purple if e.get("idx") == fl_idx else P.text2}),
                    (" ".join(e.get("tyres", [])), {"fg": P.text2, "mono": True}),
                    (str(e.get("pit_stops", 0)), {"align": "c", "fg": P.text2}),
                ])
            else:
                b = e.get("best_lap_ms") or 0
                rows.append([
                    ("", {"pos": e["position"]}),
                    (name, name_st),
                    (fmt_lap(b), {"mono": True, "fg": P.purple if b and b == best else P.text}),
                    ("" if not b or b == best else fmt_gap(b - best), {"mono": True, "fg": P.text2}),
                    (str(e.get("laps_completed") or e.get("laps") or 0), {"align": "c", "fg": P.text2}),
                ])
            hl.append(P.accent_dim if key in players else None)
        t.set_rows(rows, hl)
        t.fit_height()
        return t
