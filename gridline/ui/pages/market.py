"""Contracts — rating, market value, current deal and offers from other teams."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QMessageBox, QVBoxLayout

from ...career import market
from ...career.engine import CareerState
from ...career.models import Offer
from ...telemetry import constants as C
from ..theme import P, font
from ..widgets.charts import LineChart, Series
from ..widgets.common import (
    Card, Chip, EmptyState, RoundedBar, StatBlock, TeamBadge, button, clear_layout, fmt_money, label,
)
from .base import Page

PART_NAMES = {
    "race": "Race result vs car", "qualifying": "Qualifying vs car", "teammate": "Gap to team-mate",
    "consistency": "Lap consistency", "practice": "Practice pace", "discipline": "Penalties",
}
PART_SCALE = {"race": 16, "qualifying": 10, "teammate": 8, "consistency": 5, "practice": 3, "discipline": 10}


class OfferCard(QFrame):
    def __init__(self, page: "MarketPage", offer: Offer, st: CareerState, actionable: bool):
        super().__init__()
        colour = C.team_colour(offer.team_key)
        self.setStyleSheet(f"QFrame#Offer {{ background: {P.card2}; border: 1px solid {P.line2};"
                           f" border-left: 3px solid {colour}; border-radius: 9px; }}")
        self.setObjectName("Offer")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.addWidget(TeamBadge(offer.team_key))
        name = label(C.team_name(offer.team_key))
        name.setFont(font(13, QFont.Weight.Bold))
        top.addWidget(name)
        top.addStretch(1)
        if offer.kind == "renewal":
            top.addWidget(Chip("RENEWAL", "accent"))
        status = {"accepted": ("SIGNED", "ok"), "declined": ("DECLINED", "muted"), "expired": ("EXPIRED", "muted")}
        if offer.status in status:
            top.addWidget(Chip(*status[offer.status]))
        v.addLayout(top)

        grid = QHBoxLayout()
        grid.setSpacing(22)
        start = st.season_label(offer.season + 1)
        end = st.season_label(offer.season + offer.years)
        for cap, val in (("Salary", f"{fmt_money(offer.salary)} / season"),
                         ("Length", f"{offer.years} season{'s' if offer.years > 1 else ''}  ({start}–{end})" if offer.years > 1 else f"1 season  ({start})"),
                         ("Win bonus", fmt_money(offer.win_bonus)), ("Podium bonus", fmt_money(offer.podium_bonus))):
            b = StatBlock(cap, val)
            b.val.setFont(font(11, QFont.Weight.DemiBold))
            grid.addWidget(b)
        grid.addStretch(1)
        v.addLayout(grid)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(label("Interest", "faint"))
        bar = RoundedBar(offer.interest, centred=False, colour=colour)
        bar.setFixedWidth(110)
        bottom.addWidget(bar)
        if offer.status == "open":
            n = len(st.seasons[offer.season].calendar)
            exp = "Expires when the season ends" if offer.expires_after_round >= n else \
                f"Expires after round {offer.expires_after_round}"
            bottom.addWidget(label(f"  ·  {exp}", "faint"))
        bottom.addStretch(1)
        if actionable and offer.status == "open":
            decline = button("Decline", "ghost")
            accept = button("Sign", "primary")
            decline.clicked.connect(lambda: page.respond(offer, False))
            accept.clicked.connect(lambda: page.respond(offer, True))
            bottom.addWidget(decline)
            bottom.addWidget(accept)
        v.addLayout(bottom)


class MarketPage(Page):
    title = "Contracts"

    def __init__(self, core):
        super().__init__(core)
        cols = QHBoxLayout()
        cols.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)
        right = QVBoxLayout()
        right.setSpacing(18)
        cols.addLayout(left, 5)
        cols.addLayout(right, 6)
        self.body.addLayout(cols)
        self.body.addStretch(1)

        # rating
        self.rating_card = Card("Driver rating", padding=20)
        top = QHBoxLayout()
        top.setSpacing(26)
        self.r_now = StatBlock("Rating")
        self.r_now.val.setProperty("role", "big")
        self.r_value = StatBlock("Market value")
        self.r_best = StatBlock("Peak")
        for w in (self.r_now, self.r_value, self.r_best):
            top.addWidget(w)
        top.addStretch(1)
        self.rating_card.add(top)
        self.chart = LineChart(170, y_min=35, y_max=100, empty_text="Your rating appears after your first weekend")
        self.rating_card.add(self.chart)
        self.rating_card.add(label("LAST WEEKEND", "section"))
        self.parts_grid = QGridLayout()
        self.parts_grid.setHorizontalSpacing(14)
        self.parts_grid.setVerticalSpacing(8)
        self.rating_card.add(self.parts_grid)
        self.rating_card.add(label("The rating judges you against your car: the team's AI drivers set the "
                                   "benchmark, so out-performing a slow car counts as much as winning in a fast one.",
                                   "faint", wrap=True))
        left.addWidget(self.rating_card)

        # contract
        self.contract_card = Card("Current contract", padding=20)
        self.contract_box = QVBoxLayout()
        self.contract_box.setSpacing(10)
        self.contract_card.add(self.contract_box)
        left.addWidget(self.contract_card)

        # offers
        self.offers_card = Card("Offers", padding=18)
        self.windows_lbl = label("", "faint")
        self.offers_card.header.addWidget(self.windows_lbl)
        self.offers_box = QVBoxLayout()
        self.offers_box.setSpacing(12)
        self.offers_card.add(self.offers_box)
        right.addWidget(self.offers_card)

        self.grid_card = Card("Player drivers", padding=18)
        self.grid_box = QVBoxLayout()
        self.grid_box.setSpacing(10)
        self.grid_card.add(self.grid_box)
        right.addWidget(self.grid_card)
        right.addStretch(1)

    def respond(self, offer: Offer, accept: bool) -> None:
        if accept:
            st = self.core.state
            msg = (f"Sign with {C.team_name(offer.team_key)} for {offer.years} season(s) at "
                   f"{fmt_money(offer.salary)} a season, starting {st.season_label(offer.season + 1)}?\n\n"
                   "All other open offers will be declined.")
            if QMessageBox.question(self, "Sign contract", msg) != QMessageBox.StandardButton.Yes:
                return
        self.core.respond_offer(offer, accept)

    def refresh(self, st: CareerState) -> None:
        if not st.created or self.core.me not in st.members:
            return
        me = self.core.me
        season = st.season
        pts = st.ratings.get(me, [])
        r = st.rating_of(me)
        self.r_now.set(f"{r:.1f}")
        self.r_value.set(fmt_money(self.core.member_contract_value(me)))
        self.r_best.set(f"{max((p.rating for p in pts), default=r):.1f}")
        labels = [f"{st.season_label(p.season)[-2:]}·R{p.round}" if len(st.seasons) > 1 else f"R{p.round}" for p in pts]
        series = [Series("Rating", P.accent, [p.rating for p in pts], fill=True),
                  Series("Weekend score", P.text3, [p.score for p in pts], width=1.2)]
        self.chart.set_data(series, labels)

        clear_layout(self.parts_grid)
        if pts:
            last = pts[-1]
            for i, (k, v) in enumerate(sorted(last.parts.items(), key=lambda kv: -abs(kv[1]))):
                self.parts_grid.addWidget(label(PART_NAMES.get(k, k), "muted"), i, 0)
                bar = RoundedBar(v / PART_SCALE.get(k, 10))
                bar.setMinimumWidth(160)
                self.parts_grid.addWidget(bar, i, 1)
                val = label(f"{v:+.1f}")
                val.setStyleSheet(f"color: {P.ok if v >= 0 else P.bad}; font-weight: 600;")
                val.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.parts_grid.addWidget(val, i, 2)
            self.parts_grid.setColumnStretch(1, 1)
        else:
            self.parts_grid.addWidget(label("No weekends yet.", "faint"), 0, 0)

        # contract
        clear_layout(self.contract_box)
        c = st.contract_for(me)
        if c:
            row = QHBoxLayout()
            row.addWidget(TeamBadge(c.team_key))
            n = label(C.team_name(c.team_key))
            n.setFont(font(15, QFont.Weight.Bold))
            row.addWidget(n)
            row.addStretch(1)
            row.addWidget(Chip(f"Until end of {st.season_label(c.end_season)}",
                               "warn" if c.end_season <= st.current_season else "muted"))
            self.contract_box.addLayout(row)
            g = QHBoxLayout()
            g.setSpacing(22)
            for cap, val in (("Salary", f"{fmt_money(c.salary)} / season"), ("Win bonus", fmt_money(c.win_bonus)),
                             ("Podium bonus", fmt_money(c.podium_bonus)), ("Career earnings", fmt_money(st.earnings.get(me, 0)))):
                b = StatBlock(cap, val)
                b.val.setFont(font(11, QFont.Weight.DemiBold))
                g.addWidget(b)
            g.addStretch(1)
            self.contract_box.addLayout(g)
            nxt = st.next_contract(me)
            if nxt and nxt.start_season > st.current_season:
                self.contract_box.addWidget(label(
                    f"Signed for {st.season_label(nxt.start_season)}: {C.team_name(nxt.team_key)}, "
                    f"{fmt_money(nxt.salary)} / season until {st.season_label(nxt.end_season)}.", "muted", wrap=True))
            elif c.end_season <= st.current_season:
                self.contract_box.addWidget(label(
                    "Your deal runs out this season. If you don't sign anything, your team keeps you on a one-year "
                    "extension at market value.", "faint", wrap=True))

        # offers
        clear_layout(self.offers_box)
        windows = market.offer_windows(len(season.calendar))
        self.windows_lbl.setText("Teams review drivers after rounds " + ", ".join(map(str, windows)))
        mine = [o for o in st.offers.values() if o.member_id == me and o.season == st.current_season]
        open_first = sorted(mine, key=lambda o: (o.status != "open", -o.made_after_round, -o.salary))
        if not open_first:
            self.offers_box.addWidget(EmptyState(
                "No offers yet",
                "Teams make their moves at fixed points in the season. Strong drives against your car's "
                "pace raise your rating, and better teams start calling.", "market"))
        for o in open_first[:8]:
            self.offers_box.addWidget(OfferCard(self, o, st, actionable=True))

        clear_layout(self.grid_box)
        for m in st.members.values():
            row = QHBoxLayout()
            row.setSpacing(12)
            mc = st.contract_for(m.id)
            row.addWidget(TeamBadge(mc.team_key if mc else None))
            col = QVBoxLayout()
            col.setSpacing(0)
            nm = label(m.display_name + ("  (you)" if m.id == me else ""))
            nm.setFont(font(10.5, QFont.Weight.DemiBold))
            col.addWidget(nm)
            detail = f"{C.team_name(mc.team_key)} · {fmt_money(mc.salary)} · until {st.season_label(mc.end_season)}" if mc else "No contract"
            nxt = st.next_contract(m.id)
            if nxt and nxt.start_season > st.current_season and mc and nxt.team_key != mc.team_key:
                detail += f"  →  {C.team_name(nxt.team_key)} from {st.season_label(nxt.start_season)}"
            col.addWidget(label(detail, "faint"))
            row.addLayout(col, 1)
            rv = label(f"{st.rating_of(m.id):.1f}")
            rv.setFont(font(13, QFont.Weight.Bold))
            row.addWidget(rv)
            self.grid_box.addLayout(row)
