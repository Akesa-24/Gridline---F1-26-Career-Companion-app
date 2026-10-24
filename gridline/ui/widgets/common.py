"""Small reusable widgets and formatting helpers."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ...telemetry import constants as C
from ..theme import P, font, qc


# ------------------------------------------------------------------ formatting
def fmt_lap(ms: int | None) -> str:
    if not ms:
        return "—"
    m, rem = divmod(int(ms), 60000)
    return f"{m}:{rem / 1000:06.3f}" if m else f"{rem / 1000:.3f}"


def fmt_gap(ms: int | None, prefix: str = "+") -> str:
    if ms is None:
        return "—"
    if ms <= 0:
        return ""
    if ms >= 60000:
        return f"{prefix}{fmt_lap(ms)}"
    return f"{prefix}{ms / 1000:.3f}"


def fmt_race_time(s: float) -> str:
    if not s:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{sec:06.3f}" if h else f"{int(m)}:{sec:06.3f}"


def fmt_money(m: float) -> str:
    if m >= 10:
        return f"€{m:.0f}M"
    if m >= 1:
        return f"€{m:.1f}M"
    return f"€{m * 1000:.0f}K"


def fmt_points(p: float) -> str:
    return f"{p:.0f}" if p == int(p) else f"{p:.1f}"


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, kind: str | None = None, icon=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if icon is not None:
        b.setIcon(icon)
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {P.line};")
    return f


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


# ------------------------------------------------------------------ containers
class Card(QFrame):
    def __init__(self, title: str | None = None, padding: int = 18, spacing: int = 10, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(padding, padding - 2, padding, padding)
        self.v.setSpacing(spacing)
        self.header = None
        if title:
            self.header = QHBoxLayout()
            self.header.setSpacing(8)
            self.title = label(title, "section")
            self.header.addWidget(self.title)
            self.header.addStretch(1)
            self.v.addLayout(self.header)

    def add_right(self, *widgets):
        row = QHBoxLayout()
        row.addStretch(1)
        for w in widgets:
            row.addWidget(w)
        self.v.addLayout(row)
        return row

    def add(self, w, stretch: int = 0):
        if isinstance(w, QWidget):
            self.v.addWidget(w, stretch)
        else:
            self.v.addLayout(w, stretch)
        return w


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = label(title, "title")
        self.subtitle = label(subtitle, "subtitle")
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        h.addLayout(col)
        h.addStretch(1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        h.addLayout(self.actions)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)


class Chip(QLabel):
    """Rounded pill used for statuses and tags."""

    STYLES = {
        "ok": (P.ok, "#0E2E25"),
        "warn": (P.warn, "#33270F"),
        "bad": (P.bad, "#35131E"),
        "accent": (P.accent2, P.accent_dim),
        "muted": (P.text2, P.card2),
        "purple": (P.purple, "#2A1A48"),
    }

    def __init__(self, text: str = "", style: str = "muted"):
        super().__init__(text)
        self.set_style(style)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_style(self, style: str) -> None:
        fg, bg = self.STYLES.get(style, self.STYLES["muted"])
        self.setStyleSheet(f"QLabel {{ color: {fg}; background: {bg}; border-radius: 9px;"
                           f" padding: 2px 9px; font-size: 8.5pt; font-weight: 700; }}")


class Dot(QWidget):
    def __init__(self, colour: str = P.text3, size: int = 8, pulse: bool = False):
        super().__init__()
        self.colour = colour
        self.setFixedSize(size + 6, size + 6)
        self._size = size
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.set_pulse(pulse)

    def set_colour(self, colour: str, pulse: bool | None = None) -> None:
        self.colour = colour
        if pulse is not None:
            self.set_pulse(pulse)
        self.update()

    def set_pulse(self, on: bool) -> None:
        if on and not self._timer.isActive():
            self._timer.start(60)
        elif not on:
            self._timer.stop()
            self._phase = 0.0

    def _tick(self) -> None:
        self._phase = (self._phase + 0.06) % 1.0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self.rect().center()
        if self._phase:
            halo = qc(self.colour, int(120 * (1 - self._phase)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            r = self._size / 2 + 3 * self._phase
            p.drawEllipse(c, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.colour))
        p.drawEllipse(c, self._size / 2, self._size / 2)


class TeamStripe(QWidget):
    """Thin vertical bar in team colour."""

    def __init__(self, team_key: str | None, width: int = 4, height: int = 0):
        super().__init__()
        self.colour = C.team_colour(team_key)
        self.setFixedWidth(width)
        if height:
            self.setFixedHeight(height)

    def set_team(self, team_key: str | None) -> None:
        self.colour = C.team_colour(team_key)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.colour))
        p.drawRoundedRect(QRectF(self.rect()), 2, 2)


class TeamBadge(QWidget):
    """Team colour block with the 3-letter code, like a timing screen."""

    def __init__(self, team_key: str | None, size: QSize = QSize(42, 22)):
        super().__init__()
        self.team_key = team_key
        self.setFixedSize(size)

    def set_team(self, team_key: str | None) -> None:
        self.team_key = team_key
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QColor(C.team_colour(self.team_key))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        bg = QColor(col)
        bg.setAlpha(40)
        p.setBrush(bg)
        p.drawRoundedRect(r, 4, 4)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(r.left(), r.top(), 3, r.height()), 1.5, 1.5)
        p.setPen(QColor(P.text))
        p.setFont(font(8, QFont.Weight.Bold))
        short = C.TEAMS_2026.get(self.team_key or "", {}).get("short", "—")
        p.drawText(r.adjusted(4, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, short)


class Avatar(QWidget):
    def __init__(self, name: str, team_key: str | None = None, size: int = 40):
        super().__init__()
        self.name = name
        self.team_key = team_key
        self.setFixedSize(size, size)

    def set(self, name: str, team_key: str | None) -> None:
        self.name, self.team_key = name, team_key
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setBrush(QColor(P.card3))
        p.setPen(QPen(QColor(C.team_colour(self.team_key)), 2))
        p.drawEllipse(r)
        initials = "".join(w[0] for w in self.name.split()[:2]).upper() or "?"
        p.setPen(QColor(P.text))
        p.setFont(font(self.width() / 3.6, QFont.Weight.Bold))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, initials)


class Segmented(QFrame):
    changed = Signal(int)

    def __init__(self, options: list[str]):
        super().__init__()
        self.setStyleSheet(f"Segmented, QFrame#Seg {{ background: {P.bg0}; border: 1px solid {P.line};"
                           f" border-radius: 8px; }}")
        self.setObjectName("Seg")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for i, opt in enumerate(options):
            b = button(opt, "seg")
            b.setCheckable(True)
            if i == 0:
                b.setChecked(True)
            self.group.addButton(b, i)
            h.addWidget(b)
        self.group.idClicked.connect(self.changed)
        self.setFixedHeight(38)

    def index(self) -> int:
        return self.group.checkedId()


class StatBlock(QWidget):
    def __init__(self, caption: str, value: str = "—", sub: str = "", align_right: bool = False):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.cap = label(caption, "section")
        self.val = label(value, "metric")
        self.sub = label(sub, "faint")
        for w in (self.cap, self.val, self.sub):
            if align_right:
                w.setAlignment(Qt.AlignmentFlag.AlignRight)
            v.addWidget(w)

    def set(self, value: str, sub: str = "", colour: str | None = None) -> None:
        self.val.setText(value)
        self.sub.setText(sub or "\u00a0")
        self.val.setStyleSheet(f"color: {colour};" if colour else "")


class EmptyState(QWidget):
    def __init__(self, title: str, body: str, icon_name: str | None = None):
        super().__init__()
        from .icons import pixmap
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 36, 24, 36)
        v.setSpacing(8)
        v.addStretch(1)
        if icon_name:
            ic = QLabel()
            ic.setPixmap(pixmap(icon_name, P.text3, 34, 1.4))
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(ic)
        t = label(title)
        t.setFont(font(13, QFont.Weight.DemiBold))
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body = label(body, "muted", wrap=True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.setMaximumWidth(520)
        v.addWidget(t)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.body)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(2)


class Toast(QFrame):
    """Transient notification in the bottom-right corner of its parent."""

    COLOURS = {"ok": P.ok, "info": P.accent2, "warn": P.warn, "error": P.bad}

    def __init__(self, parent: QWidget, level: str, text: str):
        super().__init__(parent)
        colour = self.COLOURS.get(level, P.accent2)
        self.setStyleSheet(f"QFrame {{ background: {P.card3}; border: 1px solid {P.line2};"
                           f" border-left: 3px solid {colour}; border-radius: 8px; }}"
                           f" QLabel {{ background: transparent; border: none; }}")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 16, 10)
        lb = label(text, wrap=True)
        lb.setMaximumWidth(380)
        h.addWidget(lb)
        self.adjustSize()
        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim = QPropertyAnimation(self.effect, b"opacity", self)
        self.anim.setDuration(220)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.show()
        self.raise_()
        self.anim.start()
        QTimer.singleShot(4200 if level != "error" else 7000, self._fade)

    def _fade(self):
        self.anim.setDirection(QPropertyAnimation.Direction.Backward)
        self.anim.finished.connect(self.deleteLater)
        self.anim.start()


class RoundedBar(QWidget):
    """Horizontal value bar (-1..1 centred or 0..1)."""

    def __init__(self, value: float = 0.0, centred: bool = True, colour: str = P.accent):
        super().__init__()
        self.value = value
        self.centred = centred
        self.colour = colour
        self.setFixedHeight(8)

    def set_value(self, v: float) -> None:
        self.value = max(-1.0, min(1.0, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(P.card3))
        p.drawRoundedRect(r, 4, 4)
        if self.centred:
            mid = r.center().x()
            w = r.width() / 2 * abs(self.value)
            col = P.ok if self.value >= 0 else P.bad
            bar = QRectF(mid, r.top(), w, r.height()) if self.value >= 0 else QRectF(mid - w, r.top(), w, r.height())
            p.setBrush(QColor(col))
            p.drawRoundedRect(bar, 4, 4)
            p.setBrush(QColor(P.text3))
            p.drawRect(QRectF(mid - 0.5, r.top(), 1, r.height()))
        else:
            p.setBrush(QColor(self.colour))
            p.drawRoundedRect(QRectF(r.left(), r.top(), r.width() * max(0, self.value), r.height()), 4, 4)


def rounded_path(r: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    return path
