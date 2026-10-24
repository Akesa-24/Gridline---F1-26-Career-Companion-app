"""Hand-drawn line icons (QPainterPath), so the app ships no icon font or emoji."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _paint(name: str, p: QPainter, s: float) -> None:
    u = s / 24.0

    def pt(x, y):
        return QPointF(x * u, y * u)

    path = QPainterPath()
    if name == "paddock":   # dashboard tiles
        for x, y, w, h in ((3, 3, 8, 10), (13, 3, 8, 6), (13, 11, 8, 10), (3, 15, 8, 6)):
            path.addRoundedRect(QRectF(x * u, y * u, w * u, h * u), 1.6 * u, 1.6 * u)
    elif name == "live":    # pulse line
        path.moveTo(pt(2, 12))
        for x, y in ((6, 12), (8.5, 6), (12, 19), (15, 9), (17, 12), (22, 12)):
            path.lineTo(pt(x, y))
    elif name == "standings":  # podium
        path.addRect(QRectF(2.5 * u, 12 * u, 6 * u, 9 * u))
        path.addRect(QRectF(9 * u, 6 * u, 6 * u, 15 * u))
        path.addRect(QRectF(15.5 * u, 14.5 * u, 6 * u, 6.5 * u))
    elif name == "calendar":
        path.addRoundedRect(QRectF(3 * u, 4.5 * u, 18 * u, 16.5 * u), 2 * u, 2 * u)
        path.moveTo(pt(3, 9.5)); path.lineTo(pt(21, 9.5))
        path.moveTo(pt(8, 2.5)); path.lineTo(pt(8, 6.5))
        path.moveTo(pt(16, 2.5)); path.lineTo(pt(16, 6.5))
    elif name == "market":  # contract / document with signature
        path.moveTo(pt(6, 2.5)); path.lineTo(pt(14.5, 2.5)); path.lineTo(pt(19, 7))
        path.lineTo(pt(19, 21.5)); path.lineTo(pt(6, 21.5)); path.closeSubpath()
        path.moveTo(pt(9, 10)); path.lineTo(pt(16, 10))
        path.moveTo(pt(9, 13.5)); path.lineTo(pt(16, 13.5))
        path.moveTo(pt(9, 18)); path.cubicTo(pt(10.5, 15.5), pt(11.5, 19.5), pt(13, 17.5))
        path.lineTo(pt(16, 17.5))
    elif name == "inbox":
        path.moveTo(pt(3, 13)); path.lineTo(pt(6, 4)); path.lineTo(pt(18, 4)); path.lineTo(pt(21, 13))
        path.lineTo(pt(21, 20)); path.lineTo(pt(3, 20)); path.closeSubpath()
        path.moveTo(pt(3, 13)); path.lineTo(pt(8.5, 13)); path.lineTo(pt(9.5, 15.5))
        path.lineTo(pt(14.5, 15.5)); path.lineTo(pt(15.5, 13)); path.lineTo(pt(21, 13))
    elif name == "settings":  # sliders
        for y, x in ((6, 15), (12, 8), (18, 13)):
            path.moveTo(pt(3, y)); path.lineTo(pt(21, y))
            path.addEllipse(pt(x, y), 2.2 * u, 2.2 * u)
    elif name == "flag":    # chequered-ish flag
        path.moveTo(pt(5, 21)); path.lineTo(pt(5, 3))
        path.lineTo(pt(19, 3)); path.lineTo(pt(16, 8)); path.lineTo(pt(19, 13)); path.lineTo(pt(5, 13))
    elif name == "sync":
        path.moveTo(pt(19.5, 9)); path.arcTo(QRectF(4 * u, 4 * u, 16 * u, 16 * u), 20, 150)
        path.moveTo(pt(4.5, 15)); path.arcTo(QRectF(4 * u, 4 * u, 16 * u, 16 * u), 200, 150)
        path.moveTo(pt(16, 9)); path.lineTo(pt(19.5, 9)); path.lineTo(pt(19.5, 5.5))
        path.moveTo(pt(8, 15)); path.lineTo(pt(4.5, 15)); path.lineTo(pt(4.5, 18.5))
    elif name == "copy":
        path.addRoundedRect(QRectF(8 * u, 8 * u, 12 * u, 13 * u), 2 * u, 2 * u)
        path.moveTo(pt(5, 16)); path.lineTo(pt(4, 16)); path.lineTo(pt(4, 3)); path.lineTo(pt(15, 3)); path.lineTo(pt(15, 5))
    elif name == "check":
        path.moveTo(pt(4.5, 12.5)); path.lineTo(pt(9.5, 17.5)); path.lineTo(pt(19.5, 6.5))
    elif name == "plus":
        path.moveTo(pt(12, 5)); path.lineTo(pt(12, 19)); path.moveTo(pt(5, 12)); path.lineTo(pt(19, 12))
    elif name == "chevron":
        path.moveTo(pt(9, 5)); path.lineTo(pt(16, 12)); path.lineTo(pt(9, 19))
    elif name == "up":
        path.moveTo(pt(12, 19)); path.lineTo(pt(12, 5)); path.moveTo(pt(6, 11)); path.lineTo(pt(12, 5)); path.lineTo(pt(18, 11))
    elif name == "down":
        path.moveTo(pt(12, 5)); path.lineTo(pt(12, 19)); path.moveTo(pt(6, 13)); path.lineTo(pt(12, 19)); path.lineTo(pt(18, 13))
    elif name == "close":
        path.moveTo(pt(6, 6)); path.lineTo(pt(18, 18)); path.moveTo(pt(18, 6)); path.lineTo(pt(6, 18))
    p.drawPath(path)


def pixmap(name: str, colour: str | QColor, size: int = 20, width: float = 1.7, dpr: float = 2.0) -> QPixmap:
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _paint(name, p, size)
    p.end()
    return pm


def icon(name: str, colour: str = "#9CABC8", active: str | None = None, size: int = 20) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, colour, size), QIcon.Mode.Normal, QIcon.State.Off)
    if active:
        ic.addPixmap(pixmap(name, active, size), QIcon.Mode.Normal, QIcon.State.On)
        ic.addPixmap(pixmap(name, active, size), QIcon.Mode.Active, QIcon.State.On)
    return ic


def logo_pixmap(size: int = 28, dpr: float = 2.0) -> QPixmap:
    """Gridline mark: two slanted grid slots with a start line."""
    from ..theme import P
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    u = size / 28
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(P.accent))
    for i, (x, y) in enumerate(((4, 5), (13, 11))):
        poly = QPainterPath()
        poly.moveTo((x + 4) * u, y * u)
        poly.lineTo((x + 12) * u, y * u)
        poly.lineTo((x + 8) * u, (y + 11) * u)
        poly.lineTo(x * u, (y + 11) * u)
        poly.closeSubpath()
        p.setBrush(QColor(P.accent) if i == 0 else QColor(P.accent2))
        p.drawPath(poly)
    p.setBrush(QColor(P.text))
    p.drawRoundedRect(QRectF(2 * u, 23.5 * u, 24 * u, 2.2 * u), 1 * u, 1 * u)
    p.end()
    return pm
