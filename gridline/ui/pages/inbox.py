"""Results inbox — every captured session, its sync status, and disputes to rule on."""
from __future__ import annotations

import time

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from ...career.engine import CareerState
from ...career.models import SessionRecord
from ...telemetry import constants as C
from ..theme import P, font
from ..widgets.common import Card, Chip, EmptyState, button, clear_layout, label
from ..widgets.table import DataTable
from .base import Page

STATUS = {"confirmed": ("Confirmed", P.ok, "#0E2E25"), "provisional": ("Provisional", P.warn, "#33270F"),
          "disputed": ("Disputed", P.bad, "#35131E"), "resolved": ("Ruled", P.accent2, P.accent_dim)}


class InboxPage(Page):
    title = "Results"

    def __init__(self, core):
        super().__init__(core)
        self.disputes_card = Card("Disputes", padding=18)
        self.disputes_box = QVBoxLayout()
        self.disputes_box.setSpacing(14)
        self.disputes_card.add(self.disputes_box)
        self.body.addWidget(self.disputes_card)

        self.log_card = Card("Captured sessions", padding=12)
        self.void_btn = button("Void selected", "danger")
        self.void_btn.clicked.connect(self._void)
        self.log_card.header.addWidget(self.void_btn)
        self.table = DataTable([("RD", 44), ("GRAND PRIX", None), ("SESSION", 150), ("STATUS", 120),
                                ("CAPTURED BY", 200), ("WHEN", 120)], row_height=38, selectable=True)
        self.log_card.add(self.table)
        self.log_empty = EmptyState("Nothing captured yet",
                                    "Finished sessions land here the moment the game shows the results screen.", "inbox")
        self.log_card.add(self.log_empty)
        self.body.addWidget(self.log_card)
        self.body.addWidget(label(
            "How results are confirmed: both PCs in the lobby capture every session. When the two copies match, "
            "the result is confirmed. If only one PC captured it, it counts as provisional. If they disagree, "
            "the career owner picks the correct one.", "faint", wrap=True))
        self.body.addStretch(1)

    def _void(self) -> None:
        r = self.table.currentRow()
        payload = self.table.payload(r) if r >= 0 else None
        if not payload:
            return
        rec: SessionRecord = payload
        if QMessageBox.question(self, "Void result",
                                f"Remove the {rec.result.get('session_name')} at round {rec.round} from the career? "
                                "Every captured copy of it is voided.") == QMessageBox.StandardButton.Yes:
            for s in rec.submissions:
                self.core.void_submission(s.uid)

    def refresh(self, st: CareerState) -> None:
        if not st.created:
            return
        owner = self.core.is_owner
        self.void_btn.setVisible(owner)
        season = st.season
        self.header.set_subtitle(f"Season {st.season_label()}")

        # disputes
        clear_layout(self.disputes_box)
        disputes = [d for d in st.disputes if d.season == st.current_season]
        self.disputes_card.setVisible(bool(disputes))
        for rec in disputes:
            self.disputes_box.addWidget(self._dispute(rec, st, owner))

        rows, payloads = [], []
        for (rnd, stype), rec in sorted(season.sessions.items(), key=lambda kv: (kv[0][0], kv[0][1]), reverse=True):
            text, fg, bg = STATUS[rec.status]
            authors = sorted({s.author for s in rec.submissions})
            names = ", ".join(st.members[a].display_name if a in st.members else "?" for a in authors)
            when = max(s.created_at for s in rec.submissions)
            override = any(s.team_override for s in rec.submissions)
            rows.append([
                (str(rnd), {"fg": P.text3, "align": "c", "bold": True}),
                (C.track_gp(season.track(rnd)), {"sub": C.track_name(rec.result.get("track_id"))}),
                (rec.result.get("session_name", C.SESSION_TYPES.get(stype, "")),
                 {"badge": "TEAM SWAP" if override else "", "badge_colours": (P.warn, "#33270F")}),
                ("", {"badge": text, "badge_colours": (fg, bg)}),
                (names, {"fg": P.text2}),
                (time.strftime("%d %b  %H:%M", time.localtime(when)), {"fg": P.text3}),
            ])
            payloads.append(rec)
        self.table.set_rows(rows, None, payloads)
        self.table.fit_height()
        self.table.setVisible(bool(rows))
        self.log_empty.setVisible(not rows)

    def _dispute(self, rec: SessionRecord, st: CareerState, owner: bool) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        head = label(f"Round {rec.round} · {C.track_gp(st.season.track(rec.round))} · "
                     f"{rec.result.get('session_name')}")
        head.setFont(font(11.5, QFont.Weight.DemiBold))
        v.addWidget(head)
        cols = QHBoxLayout()
        cols.setSpacing(14)
        latest = {}
        for s in sorted(rec.submissions, key=lambda s: s.created_at):
            latest[s.author] = s
        for s in latest.values():
            box = Card(padding=14, spacing=6)
            who = st.members[s.author].display_name if s.author in st.members else "Unknown"
            top = QHBoxLayout()
            top.addWidget(label(f"{who}'s capture"))
            top.addStretch(1)
            box.add(top)
            for e in sorted(s.result["entries"], key=lambda e: e["position"])[:6]:
                key = e.get("driver_key", "")
                nm = st.driver_name(key) if key.startswith("p:") else e.get("name", "")
                status = "" if e.get("status") == 3 else f"  {C.RESULT_STATUS.get(e.get('status'), '')}"
                box.add(label(f"{e['position']:>2}.  {nm}{status}", "muted"))
            if owner:
                b = button("Use this result", "primary")
                b.clicked.connect(lambda _=False, uid=s.uid: self.core.resolve_dispute(
                    rec.season, rec.round, rec.session_type, uid))
                box.add(b)
            cols.addWidget(box, 1)
        v.addLayout(cols)
        if not owner:
            v.addWidget(Chip("Waiting for the career owner to rule", "warn"))
        return w
