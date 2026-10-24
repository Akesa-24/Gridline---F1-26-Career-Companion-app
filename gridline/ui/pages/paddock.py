"""Paddock — the home screen: next round, the drivers, the championship at a glance."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...career.engine import CareerState
from ...telemetry import constants as C
from ..theme import P, font
from ..widgets.common import (
    Avatar, Card, Chip, StatBlock, TeamStripe, clear_layout, fmt_money, fmt_points, label, ordinal,
)
from ..widgets.table import DataTable
from .base import Page

KIND_ORDER = [("practice", "Practice"), ("qualifying", "Qualifying"), ("race", "Race")]


class SessionStep(QWidget):
    def __init__(self, name: str):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.mark = QLabel()
        self.mark.setFixedSize(22, 22)
        self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text = label(name)
        self.text.setFont(font(10, QFont.Weight.DemiBold))
        self.state = Chip("", "muted")
        h.addWidget(self.mark)
        h.addWidget(self.text)
        h.addWidget(self.state)
        h.addStretch(1)

    def set(self, done: bool, status: str | None) -> None:
        if done:
            self.mark.setText("✓")
            self.mark.setStyleSheet(f"background: {P.ok}; color: {P.bg0}; border-radius: 11px; font-weight: 700;")
        else:
            self.mark.setText("")
            self.mark.setStyleSheet(f"border: 2px solid {P.line2}; border-radius: 11px;")
        labels = {"confirmed": ("Confirmed", "ok"), "provisional": ("Awaiting 2nd PC", "warn"),
                  "disputed": ("Disputed", "bad"), "resolved": ("Ruled", "accent")}
        if status in labels:
            t, s = labels[status]
            self.state.setText(t)
            self.state.set_style(s)
            self.state.show()
        else:
            self.state.hide()


class DriverCard(Card):
    def __init__(self):
        super().__init__(padding=18, spacing=12)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.avatar = Avatar("?", None, 46)
        top.addWidget(self.avatar)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name = label("")
        self.name.setFont(font(14, QFont.Weight.Bold))
        self.team = label("", "muted")
        col.addWidget(self.name)
        col.addWidget(self.team)
        top.addLayout(col, 1)
        self.you = Chip("YOU", "accent")
        top.addWidget(self.you, 0, Qt.AlignmentFlag.AlignTop)
        self.add(top)
        grid = QHBoxLayout()
        grid.setSpacing(18)
        self.pos = StatBlock("Championship")
        self.pts = StatBlock("Points")
        self.rating = StatBlock("Rating")
        self.value = StatBlock("Market value")
        for w in (self.pos, self.pts, self.rating, self.value):
            grid.addWidget(w)
        self.add(grid)
        self.contract = label("", "faint")
        self.add(self.contract)

    def set(self, st: CareerState, member, is_me: bool, value: float) -> None:
        c = st.contract_for(member.id)
        team = c.team_key if c else None
        self.avatar.set(member.display_name, team)
        self.name.setText(member.display_name)
        self.team.setText(C.team_name(team) if team else "No contract")
        self.team.setStyleSheet(f"color: {C.team_colour(team)}; font-weight: 600;")
        self.you.setVisible(is_me)
        key = member.driver_key
        pos = st.championship_position(key)
        ds = next((d for d in st.season.drivers if d.key == key), None)
        self.pos.set(ordinal(pos) if pos else "—", f"of {len(st.season.drivers)}" if pos else "")
        self.pts.set(fmt_points(ds.points) if ds else "0",
                     f"{ds.wins} W · {ds.podiums} pod" if ds else "")
        pts = st.ratings.get(member.id, [])
        r = st.rating_of(member.id)
        delta = (pts[-1].rating - pts[-2].rating) if len(pts) >= 2 else 0.0
        arrow = "▲" if delta > 0.05 else ("▼" if delta < -0.05 else "")
        self.rating.set(f"{r:.1f}", f"{arrow} {abs(delta):.1f} last round" if arrow else "",
                        P.ok if delta > 0.05 else (P.bad if delta < -0.05 else None))
        self.value.set(fmt_money(value))
        if c:
            nxt = st.next_contract(member.id)
            tail = ""
            if nxt and nxt.team_key != c.team_key:
                tail = f"  ·  joins {C.team_name(nxt.team_key)} in {st.season_label(nxt.start_season)}"
            self.contract.setText(f"{fmt_money(c.salary)}/season  ·  until end of {st.season_label(c.end_season)}{tail}")


class PaddockPage(Page):
    title = "Paddock"

    def __init__(self, core):
        super().__init__(core)
        top = QHBoxLayout()
        top.setSpacing(18)

        # next round hero
        self.hero = Card(padding=22, spacing=6)
        self.hero.setMinimumHeight(220)
        row = QHBoxLayout()
        self.round_lbl = label("", "section")
        row.addWidget(self.round_lbl)
        row.addStretch(1)
        self.weekend_chip = Chip("", "accent")
        row.addWidget(self.weekend_chip)
        self.hero.add(row)
        self.gp = label("")
        self.gp.setFont(font(26, QFont.Weight.Bold))
        self.hero.add(self.gp)
        self.track = label("", "muted")
        self.hero.add(self.track)
        self.hero.v.addSpacing(10)
        self.steps = {k: SessionStep(n) for k, n in KIND_ORDER}
        steps_row = QHBoxLayout()
        steps_row.setSpacing(24)
        for s in self.steps.values():
            steps_row.addWidget(s)
        steps_row.addStretch(1)
        self.hero.add(steps_row)
        self.hero.v.addStretch(1)
        self.last_box = QHBoxLayout()
        self.last_box.setSpacing(18)
        self.hero.add(self.last_box)
        self.hero.v.addSpacing(6)
        self.hint = label("", "faint", wrap=True)
        self.hero.add(self.hint)
        top.addWidget(self.hero, 3)

        # season summary
        self.summary = Card("Season", padding=20)
        self.s_progress = StatBlock("Rounds")
        self.s_leader = StatBlock("Leader")
        self.s_constructor = StatBlock("Constructors' leader")
        for w in (self.s_progress, self.s_leader, self.s_constructor):
            self.summary.add(w)
        self.summary.v.addStretch(1)
        top.addWidget(self.summary, 2)
        self.body.addLayout(top)

        self.drivers_row = QHBoxLayout()
        self.drivers_row.setSpacing(18)
        self.body.addLayout(self.drivers_row)

        bottom = QHBoxLayout()
        bottom.setSpacing(18)
        self.champ = Card("Drivers' championship", padding=14)
        self.champ_table = DataTable([("POS", 48), ("DRIVER", None), ("TEAM", 130), ("PTS", 64)], row_height=34)
        self.champ.add(self.champ_table)
        bottom.addWidget(self.champ, 3)
        self.feed = Card("Activity", padding=18)
        self.feed_box = QVBoxLayout()
        self.feed_box.setSpacing(10)
        self.feed.add(self.feed_box)
        self.feed.v.addStretch(1)
        bottom.addWidget(self.feed, 2)
        self.body.addLayout(bottom)
        self.body.addStretch(1)

    def refresh(self, st: CareerState) -> None:
        if not st.created:
            return
        season = st.season
        self.header.set_subtitle(f"{st.name}  ·  Season {st.season_label()}")
        nxt = season.next_round()
        n = len(season.calendar)
        if nxt is None:
            self.round_lbl.setText(f"SEASON {st.season_label()} COMPLETE")
            leader = season.drivers[0] if season.drivers else None
            self.gp.setText(f"{leader.name} is champion" if leader else "Season complete")
            self.track.setText("The owner can start the next season from Settings.")
            self.weekend_chip.hide()
            for s in self.steps.values():
                s.hide()
            self.hint.setText("")
        else:
            tid = season.calendar[nxt - 1]
            self.round_lbl.setText(f"ROUND {nxt} OF {n}  ·  NEXT UP")
            self.gp.setText(C.track_gp(tid))
            self.track.setText(f"{C.track_name(tid)}  ·  {C.TRACKS.get(tid, {}).get('country', '')}")
            recs = {r.kind: r for (rnd, _), r in season.sessions.items() if rnd == nxt}
            started = bool(recs)
            self.weekend_chip.setText("Weekend in progress" if started else "Not started")
            self.weekend_chip.set_style("warn" if started else "accent")
            self.weekend_chip.show()
            for kind, step in self.steps.items():
                step.show()
                rec = recs.get(kind)
                step.set(rec is not None, rec.status if rec else None)
                if kind == "practice":
                    step.setVisible(st.config.get("track_practice", True))
            self.hint.setText(
                "Load into an online lobby with the 2026 cars. Sessions are picked up automatically "
                "from the game's telemetry — there's nothing to type in."
            )

        clear_layout(self.last_box)
        last = max((r for r in range(1, n + 1) if season.race(r)), default=None)
        if last:
            res = season.race(last).result
            self.last_box.addWidget(label(f"LAST RACE  ·  {C.track_gp(season.calendar[last - 1]).upper()}", "section"))
            for e in sorted(res["entries"], key=lambda e: e["position"])[:3]:
                key = e.get("driver_key", "")
                nm = st.driver_name(key) if key.startswith("p:") else e.get("name", "")
                item = QHBoxLayout()
                item.setSpacing(6)
                pos = label(str(e["position"]))
                pos.setStyleSheet(f"color: {[P.gold, P.silver, P.bronze][e['position'] - 1]}; font-weight: 700;")
                item.addWidget(pos)
                item.addWidget(TeamStripe(e.get("team_key"), 3, 16))
                item.addWidget(label(nm.split()[-1] if nm else ""))
                self.last_box.addLayout(item)
            self.last_box.addStretch(1)

        done = season.rounds_done()
        self.s_progress.set(f"{done} / {n}", f"{n - done} to go" if done < n else "Complete")
        if season.drivers and season.drivers[0].points:
            d = season.drivers[0]
            gap = d.points - season.drivers[1].points if len(season.drivers) > 1 else 0
            self.s_leader.set(d.name, f"{fmt_points(d.points)} pts  ·  +{fmt_points(gap)}")
            self.s_leader.val.setStyleSheet(f"color: {C.team_colour(d.team_key)};")
        else:
            self.s_leader.set("—", "No races yet")
        t = season.teams[0] if season.teams and season.teams[0].points else None
        self.s_constructor.set(C.team_name(t.key) if t else "—", f"{fmt_points(t.points)} pts" if t else "")
        if t:
            self.s_constructor.val.setStyleSheet(f"color: {C.team_colour(t.key)};")

        clear_layout(self.drivers_row)
        members = sorted(st.members.values(), key=lambda m: m.id != self.core.me)
        for m in members:
            card = DriverCard()
            card.set(st, m, m.id == self.core.me, self.core.member_contract_value(m.id))
            self.drivers_row.addWidget(card, 1)

        rows, hl = [], []
        player_keys = {m.driver_key for m in st.members.values()}
        for i, d in enumerate(season.drivers[:10], 1):
            rows.append([("", {"pos": i}), (d.name, {"team": d.team_key, "bold": d.key in player_keys}),
                         (C.team_name(d.team_key), {"fg": P.text2}),
                         (fmt_points(d.points), {"align": "r", "bold": True, "mono": True})])
            hl.append(P.accent_dim if d.key in player_keys else None)
        for d in season.drivers[10:]:
            if d.key in player_keys:
                i = season.drivers.index(d) + 1
                rows.append([("", {"pos": i}), (d.name, {"team": d.team_key, "bold": True}),
                             (C.team_name(d.team_key), {"fg": P.text2}),
                             (fmt_points(d.points), {"align": "r", "bold": True, "mono": True})])
                hl.append(P.accent_dim)
        self.champ_table.set_rows(rows, hl)
        self.champ_table.fit_height()
        if not rows:
            self.champ_table.setRowCount(0)
            self.champ_table.fit_height()

        clear_layout(self.feed_box)
        items = list(reversed(st.log[-8:]))
        for ts, text in items:
            row = QHBoxLayout()
            row.setSpacing(10)
            bar = TeamStripe(None, 3, 30)
            bar.colour = P.accent
            row.addWidget(bar)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(label(text, wrap=True))
            col.addWidget(label(_ago(ts), "faint"))
            row.addLayout(col, 1)
            self.feed_box.addLayout(row)


def _ago(ts: float) -> str:
    d = time.time() - ts
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    return time.strftime("%d %b %Y", time.localtime(ts))
