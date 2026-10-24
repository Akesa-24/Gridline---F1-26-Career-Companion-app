"""Main window: sidebar navigation, page stack, welcome screen and toasts."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .. import __version__
from .dialogs import CaptureReviewDialog, SetupDialog
from .pages.calendar import CalendarPage
from .pages.inbox import InboxPage
from .pages.live import LivePage
from .pages.market import MarketPage
from .pages.paddock import PaddockPage
from .pages.settings import SettingsPage
from .pages.standings import StandingsPage
from .theme import P, font
from .widgets import icons
from .widgets.common import Dot, Toast, button, label


class NavButton(QAbstractButton):
    def __init__(self, icon_name: str, text: str):
        super().__init__()
        self.icon_name = icon_name
        self.label = text
        self.badge = ""
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)
        self._pm = {False: icons.pixmap(icon_name, P.text2, 18), True: icons.pixmap(icon_name, P.text, 18)}

    def set_badge(self, text: str) -> None:
        self.badge = text
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(200, 40)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(10, 2, -10, -2)
        on = self.isChecked()
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P.card2))
            p.drawRoundedRect(r, 8, 8)
            p.setBrush(QColor(P.accent))
            p.drawRoundedRect(QRectF(r.left(), r.top() + 9, 3, r.height() - 18), 1.5, 1.5)
        elif self.underMouse():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P.card))
            p.drawRoundedRect(r, 8, 8)
        p.drawPixmap(int(r.left() + 14), int(r.center().y() - 9), self._pm[on])
        p.setPen(QColor(P.text if on else P.text2))
        p.setFont(font(10.5, QFont.Weight.DemiBold if on else QFont.Weight.Normal))
        p.drawText(QRectF(r.left() + 44, r.top(), r.width() - 80, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label)
        if self.badge:
            p.setFont(font(8, QFont.Weight.Bold))
            w = max(20, p.fontMetrics().horizontalAdvance(self.badge) + 12)
            b = QRectF(r.right() - w - 8, r.center().y() - 9, w, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(P.bad))
            p.drawRoundedRect(b, 9, 9)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(b, Qt.AlignmentFlag.AlignCenter, self.badge)


class StatusLine(QWidget):
    def __init__(self, caption: str):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        self.dot = Dot(P.text3, 7)
        h.addWidget(self.dot)
        col = QVBoxLayout()
        col.setSpacing(0)
        cap = label(caption.upper(), "section")
        cap.setStyleSheet("font-size: 7.5pt;")
        self.text = label("", "muted")
        self.text.setStyleSheet("font-size: 9pt;")
        col.addWidget(cap)
        col.addWidget(self.text)
        h.addLayout(col, 1)

    def set(self, colour: str, text: str, pulse: bool = False) -> None:
        self.dot.set_colour(colour, pulse)
        fm = self.text.fontMetrics()
        self.text.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, 150))
        self.text.setToolTip(text)


class Sidebar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(232)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 22, 0, 18)
        v.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(22, 0, 16, 0)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(26))
        brand.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        word = label("GRIDLINE")
        word.setFont(font(14, QFont.Weight.Bold))
        word.setStyleSheet("letter-spacing: 2px;")
        sub = label("F1 26 career companion", "faint")
        sub.setStyleSheet("font-size: 8.5pt;")
        col.addWidget(word)
        col.addWidget(sub)
        brand.addLayout(col)
        brand.addStretch(1)
        v.addLayout(brand)
        v.addSpacing(18)

        self.career_name = label("", "muted")
        self.career_name.setContentsMargins(24, 0, 16, 6)
        self.career_name.setStyleSheet(f"color: {P.text3}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px;")
        v.addWidget(self.career_name)

        self.group = QButtonGroup(self)
        self.buttons: dict[str, NavButton] = {}
        for key, ic, text in (("paddock", "paddock", "Paddock"), ("live", "live", "Live timing"),
                              ("standings", "standings", "Standings"), ("calendar", "calendar", "Calendar"),
                              ("market", "market", "Contracts"), ("inbox", "inbox", "Results")):
            b = NavButton(ic, text)
            self.group.addButton(b)
            self.buttons[key] = b
            v.addWidget(b)
        v.addStretch(1)
        b = NavButton("settings", "Settings")
        self.group.addButton(b)
        self.buttons["settings"] = b
        v.addWidget(b)
        v.addSpacing(14)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {P.line}; margin: 0 18px;")
        v.addWidget(line)
        v.addSpacing(12)
        st = QVBoxLayout()
        st.setContentsMargins(22, 0, 16, 0)
        st.setSpacing(10)
        self.tel = StatusLine("Telemetry")
        self.sync = StatusLine("Sync")
        st.addWidget(self.tel)
        st.addWidget(self.sync)
        v.addLayout(st)
        v.addSpacing(10)
        ver = label(f"v{__version__}", "faint")
        ver.setContentsMargins(24, 0, 0, 0)
        ver.setStyleSheet(f"color: {P.text3}; font-size: 8pt;")
        v.addWidget(ver)


class WelcomeView(QWidget):
    def __init__(self, on_create, on_join):
        super().__init__()
        self.setObjectName("Canvas")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        left = QFrame()
        left.setObjectName("Sidebar")
        left.setFixedWidth(420)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(48, 56, 48, 40)
        lv.setSpacing(14)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(46))
        lv.addWidget(logo)
        lv.addSpacing(10)
        t = label("GRIDLINE")
        t.setFont(font(30, QFont.Weight.Bold))
        t.setStyleSheet("letter-spacing: 4px;")
        lv.addWidget(t)
        lv.addWidget(label("A multiplayer career for the 2026 cars — built from your telemetry.", "muted", wrap=True))
        lv.addSpacing(24)
        for head, body in (
            ("Nothing to type in", "Practice, qualifying and race results are read from the game's UDP stream the "
                                   "moment each session ends."),
            ("Both PCs, one championship", "Results sync through a free database the career owner hosts. "
                                           "Matching captures confirm each other."),
            ("A driver market", "Your rating is measured against your car. Teams make offers; you choose where "
                                "to drive next season."),
        ):
            hh = label(head)
            hh.setFont(font(11, QFont.Weight.DemiBold))
            lv.addWidget(hh)
            lv.addWidget(label(body, "faint", wrap=True))
            lv.addSpacing(6)
        lv.addStretch(1)
        lv.addWidget(label(f"v{__version__}  ·  Not affiliated with EA, Codemasters or Formula 1.", "faint", wrap=True))
        h.addWidget(left)

        right_w = QWidget()
        right = QVBoxLayout(right_w)
        right.setContentsMargins(64, 56, 64, 56)
        right.setSpacing(18)
        right.addStretch(1)
        hdr = label("Get started")
        hdr.setFont(font(22, QFont.Weight.Bold))
        right.addWidget(hdr)
        right.addWidget(label("One player owns the career and hosts the data. Everyone else joins with an invite code.", "muted", wrap=True))
        right.addSpacing(10)
        for title, body, cta, fn, primary in (
            ("Start a career", "Pick the rules and the calendar, choose your first team, and connect a free "
                               "Supabase project to share it.", "Start a career", on_create, True),
            ("Join a career", "Got an invite code from a friend? Paste it in, pick your team and you're on the grid.",
             "Join with code", on_join, False),
        ):
            card = QFrame()
            card.setObjectName("Card")
            cv = QVBoxLayout(card)
            cv.setContentsMargins(24, 20, 24, 20)
            cv.setSpacing(8)
            tt = label(title)
            tt.setFont(font(14, QFont.Weight.Bold))
            cv.addWidget(tt)
            cv.addWidget(label(body, "muted", wrap=True))
            row = QHBoxLayout()
            row.addStretch(1)
            b = button(cta, "primary" if primary else None)
            b.clicked.connect(fn)
            row.addWidget(b)
            cv.addLayout(row)
            card.setMaximumWidth(620)
            right.addWidget(card)
        right.addStretch(2)
        h.addWidget(right_w, 1)


class MainWindow(QMainWindow):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.setWindowTitle("Gridline — F1 26 Career Companion")
        self.setWindowIcon(QIcon(icons.logo_pixmap(64)))
        self.resize(1380, 880)
        self.setMinimumSize(960, 600)

        self.root = QStackedWidget()
        self.setCentralWidget(self.root)
        self.welcome = WelcomeView(lambda: self.open_setup("create"), lambda: self.open_setup("join"))
        self.root.addWidget(self.welcome)

        app = QWidget()
        h = QHBoxLayout(app)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = Sidebar()
        h.addWidget(self.sidebar)
        self.pages = QStackedWidget()
        h.addWidget(self.pages, 1)
        self.root.addWidget(app)

        self.page_map = {
            "paddock": PaddockPage(core), "live": LivePage(core), "standings": StandingsPage(core),
            "calendar": CalendarPage(core), "market": MarketPage(core), "inbox": InboxPage(core),
            "settings": SettingsPage(core),
        }
        for key, page in self.page_map.items():
            self.pages.addWidget(page)
            self.sidebar.buttons[key].clicked.connect(lambda _=False, k=key: self.show_page(k))
        self.page_map["settings"].new_career_requested.connect(self._new_or_join)
        self.sidebar.buttons["paddock"].setChecked(True)

        core.state_changed.connect(self.on_state)
        core.careers_changed.connect(self._route)
        core.telemetry_state.connect(self.on_telemetry)
        core.sync_state.connect(self.on_sync)
        core.toast.connect(self.show_toast)
        core.capture_needs_review.connect(self.review_capture)
        self.on_telemetry(*core.telemetry)
        self._route()

    # ------------------------------------------------------------------
    def _route(self) -> None:
        has = bool(self.core.career)
        self.root.setCurrentIndex(1 if has else 0)

    def show_page(self, key: str) -> None:
        page = self.page_map[key]
        self.sidebar.buttons[key].setChecked(True)
        self.pages.setCurrentWidget(page)
        page.refresh(self.core.state)

    def on_state(self, st) -> None:
        self._route()
        if not st.created:
            return
        self.sidebar.career_name.setText(st.name.upper())
        current = self.pages.currentWidget()
        current.refresh(st)
        for p in self.page_map.values():
            if p is not current:
                p._dirty = True  # refreshed on next show
        disputes = len([d for d in st.disputes if d.season == st.current_season])
        self.sidebar.buttons["inbox"].set_badge(str(disputes) if disputes else "")
        offers = len(st.open_offers(self.core.me))
        self.sidebar.buttons["market"].set_badge(str(offers) if offers else "")

    def on_telemetry(self, state: str, msg: str) -> None:
        colours = {"receiving": (P.ok, True), "listening": (P.accent, False), "error": (P.bad, False)}
        c, pulse = colours.get(state, (P.text3, False))
        self.sidebar.tel.set(c, msg, pulse)

    def on_sync(self, state: str, detail: str) -> None:
        pending = self.core.pending_count()
        text = {"online": "Up to date" if not pending else f"{pending} waiting to upload",
                "offline": "Offline — will retry", "error": detail, "schema": "Database not set up",
                "local": "This PC only"}.get(state, detail)
        colour = {"online": P.ok, "offline": P.warn, "error": P.bad, "schema": P.bad}.get(state, P.text3)
        self.sidebar.sync.set(colour, text)

    def show_toast(self, level: str, text: str) -> None:
        t = Toast(self, level, text)
        t.adjustSize()
        existing = [w for w in self.findChildren(Toast) if w is not t and w.isVisible()]
        y = self.height() - t.height() - 24 - sum(w.height() + 10 for w in existing)
        t.move(self.width() - t.width() - 24, max(20, y))

    def review_capture(self, cap) -> None:
        dlg = CaptureReviewDialog(self.core, cap, self)
        if dlg.exec():
            self.core.commit_capture(cap)
        else:
            self.core.discard_capture(cap)

    def open_setup(self, mode: str) -> None:
        dlg = SetupDialog(self.core, mode, self)
        dlg.exec()
        self._route()
        if self.core.career:
            self.show_page("paddock")

    def _new_or_join(self) -> None:
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        a1 = m.addAction("Start a new career")
        a2 = m.addAction("Join with an invite code")
        act = m.exec(self.cursor().pos())
        if act == a1:
            self.open_setup("create")
        elif act == a2:
            self.open_setup("join")

    def closeEvent(self, e):
        self.core.shutdown()
        super().closeEvent(e)
