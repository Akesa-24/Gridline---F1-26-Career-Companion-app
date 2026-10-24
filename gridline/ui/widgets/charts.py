"""Custom painted charts — line chart with hover readout."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..theme import P, font


@dataclass
class Series:
    name: str
    colour: str
    values: list[float | None]
    fill: bool = False
    width: float = 2.0


class LineChart(QWidget):
    def __init__(self, height: int = 180, y_min: float | None = None, y_max: float | None = None,
                 y_fmt=lambda v: f"{v:.0f}", empty_text: str = "No data yet"):
        super().__init__()
        self.setMinimumHeight(height)
        self.series: list[Series] = []
        self.x_labels: list[str] = []
        self.y_min, self.y_max = y_min, y_max
        self.y_fmt = y_fmt
        self.empty_text = empty_text
        self.hover_i: int | None = None
        self.setMouseTracking(True)

    def set_data(self, series: list[Series], x_labels: list[str]) -> None:
        self.series = series
        self.x_labels = x_labels
        self.update()

    def _bounds(self):
        vals = [v for s in self.series for v in s.values if v is not None]
        lo = self.y_min if self.y_min is not None else (min(vals) if vals else 0)
        hi = self.y_max if self.y_max is not None else (max(vals) if vals else 1)
        if self.y_min is None and vals:
            lo = min(lo, min(vals))
        if hi - lo < 1e-6:
            hi = lo + 1
        pad = (hi - lo) * 0.08
        return lo - (pad if self.y_min is None else 0), hi + (pad if self.y_max is None else 0)

    def _plot_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(38, 12, -14, -26)

    def _x(self, i: int, n: int, pr: QRectF) -> float:
        return pr.left() + (pr.width() * i / max(n - 1, 1) if n > 1 else pr.width() / 2)

    def mouseMoveEvent(self, e):
        n = len(self.x_labels)
        if not n:
            return
        pr = self._plot_rect()
        x = e.position().x()
        i = round((x - pr.left()) / max(pr.width(), 1) * (n - 1)) if n > 1 else 0
        i = max(0, min(n - 1, i))
        if i != self.hover_i:
            self.hover_i = i
            self.update()

    def leaveEvent(self, _):
        self.hover_i = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pr = self._plot_rect()
        n = len(self.x_labels)
        if not n or not any(v is not None for s in self.series for v in s.values):
            p.setPen(QColor(P.text3))
            p.setFont(font(9.5))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return
        lo, hi = self._bounds()

        def y(v):
            return pr.bottom() - (v - lo) / (hi - lo) * pr.height()

        # grid
        p.setFont(font(8))
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            yy = y(v)
            p.setPen(QPen(QColor(P.line), 1, Qt.PenStyle.SolidLine if k == 0 else Qt.PenStyle.DotLine))
            p.drawLine(QPointF(pr.left(), yy), QPointF(pr.right(), yy))
            p.setPen(QColor(P.text3))
            p.drawText(QRectF(0, yy - 8, pr.left() - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.y_fmt(v))
        step = max(1, n // 12)
        for i, lb in enumerate(self.x_labels):
            if i % step and i != n - 1:
                continue
            xx = self._x(i, n, pr)
            p.drawText(QRectF(xx - 30, pr.bottom() + 6, 60, 16), Qt.AlignmentFlag.AlignHCenter, lb)

        if self.hover_i is not None:
            xx = self._x(self.hover_i, n, pr)
            p.setPen(QPen(QColor(P.line2), 1))
            p.drawLine(QPointF(xx, pr.top()), QPointF(xx, pr.bottom()))

        for s in self.series:
            pts = [(self._x(i, n, pr), y(v)) for i, v in enumerate(s.values) if v is not None]
            if not pts:
                continue
            path = QPainterPath(QPointF(*pts[0]))
            for a, b in zip(pts, pts[1:]):
                cx = (a[0] + b[0]) / 2
                path.cubicTo(QPointF(cx, a[1]), QPointF(cx, b[1]), QPointF(*b))
            if s.fill and len(pts) > 1:
                area = QPainterPath(path)
                area.lineTo(QPointF(pts[-1][0], pr.bottom()))
                area.lineTo(QPointF(pts[0][0], pr.bottom()))
                area.closeSubpath()
                g = QLinearGradient(0, pr.top(), 0, pr.bottom())
                c1 = QColor(s.colour); c1.setAlpha(70)
                c2 = QColor(s.colour); c2.setAlpha(0)
                g.setColorAt(0, c1)
                g.setColorAt(1, c2)
                p.fillPath(area, g)
            pen = QPen(QColor(s.colour), s.width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setBrush(QColor(P.bg1))
            p.setPen(QPen(QColor(s.colour), 1.8))
            if len(pts) <= 30:
                for x_, y_ in pts:
                    p.drawEllipse(QPointF(x_, y_), 2.8, 2.8)

        if self.hover_i is not None:
            lines = []
            for s in self.series:
                if self.hover_i < len(s.values) and s.values[self.hover_i] is not None:
                    lines.append((s.colour, f"{s.name}  {self.y_fmt(s.values[self.hover_i])}"))
            if lines:
                p.setFont(font(8.5, QFont.Weight.DemiBold))
                fm = p.fontMetrics()
                w = max(fm.horizontalAdvance(t) for _, t in lines) + 30
                h = 22 + 17 * len(lines)
                xx = self._x(self.hover_i, n, pr)
                bx = QRectF(xx + 10 if xx + 10 + w < pr.right() else xx - 10 - w, pr.top(), w, h)
                p.setPen(QPen(QColor(P.line2), 1))
                p.setBrush(QColor(P.card3))
                p.drawRoundedRect(bx, 6, 6)
                p.setPen(QColor(P.text3))
                p.drawText(bx.adjusted(10, 5, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.x_labels[self.hover_i])
                for k, (c, t) in enumerate(lines):
                    yy = bx.top() + 24 + k * 17
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(c))
                    p.drawEllipse(QPointF(bx.left() + 14, yy + 7), 3.5, 3.5)
                    p.setPen(QColor(P.text))
                    p.drawText(QRectF(bx.left() + 24, yy, w, 15), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, t)
