"""Standings — drivers' and constructors' championships as a results matrix."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout

from ...career.engine import CareerState
from ...telemetry import constants as C
from ..theme import P
from ..widgets.charts import LineChart, Series
from ..widgets.common import Card, Segmented, clear_layout, fmt_points, label
from ..widgets.table import DataTable
from .base import Page

CELL = {
    1: ("#4B3D10", P.gold), 2: ("#323B4C", P.silver), 3: ("#43301F", P.bronze),
    "pts": ("#10342B", P.ok), "out": ("", P.text2), "dnf": ("#3A1621", P.bad),
}


def cell_style(cell) -> dict:
    if cell is None:
        return {"cell": ("", P.text3)}
    if cell.status in (4, 5, 6, 7):
        bg, fg = CELL["dnf"]
    elif cell.position in (1, 2, 3):
        bg, fg = CELL[cell.position]
    elif cell.points > 0:
        bg, fg = CELL["pts"]
    else:
        bg, fg = CELL["out"]
    st = {"cell": (bg, fg), "bold": cell.pole}
    if cell.fastest_lap:
        st["outline"] = P.purple
    return st


class StandingsPage(Page):
    title = "Standings"

    def __init__(self, core):
        super().__init__(core)
        self.mode = Segmented(["Drivers", "Constructors"])
        self.mode.changed.connect(lambda _: self.refresh(self.core.state))
        self.season_box = QComboBox()
        self.season_box.setMinimumWidth(110)
        self.season_box.currentIndexChanged.connect(lambda _: self.refresh(self.core.state, keep_season=True))
        self.header.actions.addWidget(self.season_box)
        self.header.actions.addWidget(self.mode)

        self.matrix_card = Card(padding=12)
        self.matrix_holder = QVBoxLayout()
        self.matrix_card.add(self.matrix_holder)
        legend = QHBoxLayout()
        legend.setSpacing(16)
        for text, colour in (("Winner", P.gold), ("Podium", P.bronze), ("Points", P.ok),
                             ("Retired", P.bad), ("Bold = pole", P.text2), ("Purple ring = fastest lap", P.purple)):
            lb = label(text, "faint")
            lb.setStyleSheet(f"color: {colour};")
            legend.addWidget(lb)
        legend.addStretch(1)
        self.matrix_card.add(legend)
        self.body.addWidget(self.matrix_card)

        self.chart_card = Card("Championship progression", padding=18)
        self.chart = LineChart(240, y_min=0, empty_text="The chart fills in after the first race")
        self.chart_card.add(self.chart)
        self.body.addWidget(self.chart_card)
        self.body.addStretch(1)
        self.table = None
        self._cols = None

    def _ensure_table(self, cols):
        if cols == self._cols and self.table is not None:
            return
        clear_layout(self.matrix_holder)
        self.table = DataTable(cols, row_height=32)
        self.table.horizontalHeader().setStyleSheet("QHeaderView::section { padding: 6px 0px; }")
        for i in range(2, len(cols) - 1):
            self.table.horizontalHeaderItem(i).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.matrix_holder.addWidget(self.table)
        self._cols = cols

    def refresh(self, st: CareerState, keep_season: bool = False) -> None:
        if not st.created:
            return
        if self.season_box.count() != len(st.seasons):
            keep = self.season_box.currentData()
            self.season_box.blockSignals(True)
            self.season_box.clear()
            for n in sorted(st.seasons, reverse=True):
                self.season_box.addItem(st.season_label(n), n)
            if keep in st.seasons and keep != st.current_season - 1:
                self.season_box.setCurrentIndex(self.season_box.findData(keep))
            self.season_box.blockSignals(False)
        season_no = self.season_box.currentData()
        if season_no not in st.seasons:
            season_no = st.current_season
        season = st.seasons[season_no]
        self.header.set_subtitle(f"Season {st.season_label(season_no)}  ·  {season.rounds_done()} of "
                                 f"{len(season.calendar)} rounds")
        codes = [C.TRACKS.get(t, {}).get("country", str(t))[:3] for t in season.calendar]
        players = {m.driver_key for m in st.members.values()}
        drivers_mode = self.mode.index() == 0

        cols = [("POS", 46), ("DRIVER" if drivers_mode else "TEAM", 190)]
        cols += [(c, 36) for c in codes] + [("PTS", None)]
        self._ensure_table(cols)
        rows, hl = [], []
        if drivers_mode:
            for i, d in enumerate(season.drivers, 1):
                row = [("", {"pos": i}), (d.name, {"team": d.team_key, "bold": d.key in players})]
                for r in range(1, len(season.calendar) + 1):
                    c = d.cells.get(r)
                    row.append((c.label if c else "", cell_style(c)))
                row.append((fmt_points(d.points), {"align": "r", "bold": True, "mono": True}))
                rows.append(row)
                hl.append(P.accent_dim if d.key in players else None)
        else:
            for i, t in enumerate(season.teams, 1):
                row = [("", {"pos": i}), (C.team_name(t.key), {"team": t.key, "bold": True})]
                for r in range(1, len(season.calendar) + 1):
                    v = t.cells.get(r)
                    raced = season.race(r) is not None
                    if v is None:
                        row.append(("" if not raced else "0", {"cell": ("", P.text3)}))
                    else:
                        row.append((fmt_points(v), {"cell": (CELL["pts"][0] if v > 0 else "", P.ok if v > 0 else P.text2)}))
                row.append((fmt_points(t.points), {"align": "r", "bold": True, "mono": True}))
                rows.append(row)
                hl.append(None)
        self.table.set_rows(rows, hl)
        self.table.horizontalHeader().setMinimumSectionSize(36)
        self.table.fit_height(extra=12)

        # progression chart
        done_rounds = [r for r in range(1, len(season.calendar) + 1) if season.race(r)]
        series = []
        if drivers_mode:
            pick = season.drivers[:4] + [d for d in season.drivers[4:] if d.key in players]
            palette = [C.team_colour(d.team_key) for d in pick]
            for d, col in zip(pick, palette):
                cum, total = [], 0.0
                for r in done_rounds:
                    c = d.cells.get(r)
                    total += c.points if c else 0
                    cum.append(total)
                series.append(Series(d.name, col, cum, width=2.6 if d.key in players else 1.8))
        else:
            for t in season.teams[:5]:
                cum, total = [], 0.0
                for r in done_rounds:
                    total += t.cells.get(r, 0.0)
                    cum.append(total)
                series.append(Series(C.team_name(t.key), C.team_colour(t.key), cum))
        self.chart.set_data(series, [codes[r - 1] for r in done_rounds])
