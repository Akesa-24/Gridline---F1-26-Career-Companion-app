"""Timing-screen style table: QTableWidget plus a delegate that paints rich cells."""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableWidget,
    QTableWidgetItem,
)

from ...telemetry import constants as C
from ..theme import P, font

STYLE = Qt.ItemDataRole.UserRole + 10
ROW_HL = Qt.ItemDataRole.UserRole + 11
PAYLOAD = Qt.ItemDataRole.UserRole + 12


class RichDelegate(QStyledItemDelegate):
    def __init__(self, table: "DataTable"):
        super().__init__(table)
        self.table = table

    def paint(self, p: QPainter, opt: QStyleOptionViewItem, idx) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(opt.rect)
        st: dict = idx.data(STYLE) or {}
        text = idx.data(Qt.ItemDataRole.DisplayRole) or ""
        row_hl = idx.siblingAtColumn(0).data(ROW_HL)

        # row background
        hovered = self.table.hover_row == idx.row()
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        if row_hl:
            p.fillRect(r, QColor(row_hl))
        if selected and self.table.selectable:
            p.fillRect(r, QColor(P.card3))
        elif hovered:
            p.fillRect(r, QColor(255, 255, 255, 8))
        if self.table.row_lines:
            p.setPen(QPen(QColor(P.line), 1))
            p.drawLine(r.bottomLeft(), r.bottomRight())

        inner = r.adjusted(8, 0, -8, 0)
        align = {"r": Qt.AlignmentFlag.AlignRight, "c": Qt.AlignmentFlag.AlignHCenter}.get(
            st.get("align", ""), Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter

        if "team" in st:
            col = QColor(C.team_colour(st["team"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            bar_h = min(r.height() - 12, 20)
            p.drawRoundedRect(QRectF(r.left() + 6, r.center().y() - bar_h / 2, 3.5, bar_h), 1.5, 1.5)
            inner = r.adjusted(18, 0, -8, 0)

        if "pos" in st:
            pos = st["pos"]
            box = QRectF(r.center().x() - 13, r.center().y() - 11, 26, 22)
            colours = {1: P.gold, 2: P.silver, 3: P.bronze}
            if pos in colours and st.get("medal", True):
                p.setPen(Qt.PenStyle.NoPen)
                c = QColor(colours[pos])
                c.setAlpha(46)
                p.setBrush(c)
                p.drawRoundedRect(box, 5, 5)
                p.setPen(QColor(colours[pos]))
            else:
                p.setPen(QColor(P.text2 if pos else P.text3))
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, str(pos) if pos else "—")
            p.restore()
            return

        if "cell" in st:
            bg, fg = st["cell"]
            box = r.adjusted(2, 4, -2, -4)
            p.setPen(Qt.PenStyle.NoPen)
            if bg:
                p.setBrush(QColor(bg))
                p.drawRoundedRect(box, 4, 4)
            if st.get("outline"):
                p.setPen(QPen(QColor(st["outline"]), 1.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(box.adjusted(0.8, 0.8, -0.8, -0.8), 4, 4)
            p.setPen(QColor(fg))
            p.setFont(font(9, QFont.Weight.Bold if st.get("bold") else QFont.Weight.DemiBold))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
            p.restore()
            return

        if "tyre" in st:
            t = st["tyre"]
            cx = inner.left() + 10 if st.get("align") != "c" else r.center().x()
            if t:
                col = QColor(C.TYRE_COLOURS.get(t, P.text3))
                p.setPen(QPen(col, 2.2))
                p.setBrush(QColor(P.bg0))
                p.drawEllipse(QRectF(cx - 9, r.center().y() - 9, 18, 18))
                p.setPen(col)
                p.setFont(font(7.5, QFont.Weight.Bold))
                p.drawText(QRectF(cx - 9, r.center().y() - 9, 18, 18), Qt.AlignmentFlag.AlignCenter, t)
            if text:
                p.setPen(QColor(P.text2))
                p.setFont(font(9, mono=True))
                p.drawText(QRectF(cx + 14, r.top(), 60, r.height()),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            p.restore()
            return

        if "badge" in st and st["badge"]:
            fg, bg = st.get("badge_colours", (P.accent2, P.accent_dim))
            p.setFont(font(7.5, QFont.Weight.Bold))
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(st["badge"]) + 12
            tw = 0
            if text:
                p.setFont(font(10, QFont.Weight.DemiBold if st.get("bold") else QFont.Weight.Normal))
                tw = p.fontMetrics().horizontalAdvance(text)
            bx = QRectF(inner.left() + tw + 8, r.center().y() - 8, w, 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(bg))
            p.drawRoundedRect(bx, 8, 8)
            p.setPen(QColor(fg))
            p.setFont(font(7.5, QFont.Weight.Bold))
            p.drawText(bx, Qt.AlignmentFlag.AlignCenter, st["badge"])

        p.setPen(QColor(st.get("fg", P.text)))
        weight = QFont.Weight.DemiBold if st.get("bold") else QFont.Weight.Normal
        p.setFont(font(st.get("size", 9.5 if st.get("mono") else 10), weight, mono=st.get("mono", False)))
        if st.get("sub"):
            top = QRectF(inner.left(), r.top() + 4, inner.width(), r.height() / 2)
            p.drawText(top, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                       p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(inner.width())))
            p.setPen(QColor(P.text3))
            p.setFont(font(8.5))
            p.drawText(QRectF(inner.left(), r.center().y() + 1, inner.width(), r.height() / 2 - 4),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, st["sub"])
        else:
            p.drawText(inner, align, p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(inner.width())))
        p.restore()

    def sizeHint(self, opt, idx) -> QSize:
        return QSize(60, self.table.row_height)


class DataTable(QTableWidget):
    def __init__(self, columns: list[tuple[str, int | None]], row_height: int = 38,
                 selectable: bool = False, row_lines: bool = True):
        super().__init__(0, len(columns))
        self.row_height = row_height
        self.selectable = selectable
        self.row_lines = row_lines
        self.hover_row = -1
        self.setItemDelegate(RichDelegate(self))
        self.setHorizontalHeaderLabels([c[0] for c in columns])
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(row_height)
        self.setShowGrid(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection if selectable
                              else QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        hh = self.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for i, (_, w) in enumerate(columns):
            if w is None:
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            else:
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
                self.setColumnWidth(i, w)

    def mouseMoveEvent(self, e):
        row = self.rowAt(int(e.position().y()))
        if row != self.hover_row:
            self.hover_row = row
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self.hover_row = -1
        self.viewport().update()
        super().leaveEvent(e)

    def set_rows(self, rows: list[list[tuple[str, dict] | str]], highlights: list[str | None] | None = None,
                 payloads: list | None = None) -> None:
        self.setUpdatesEnabled(False)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                text, style = (cell, {}) if isinstance(cell, str) else cell
                item = self.item(r, c)
                if item is None:
                    item = QTableWidgetItem()
                    self.setItem(r, c, item)
                item.setText(text)
                item.setData(STYLE, style)
                if c == 0:
                    item.setData(ROW_HL, highlights[r] if highlights else None)
                    item.setData(PAYLOAD, payloads[r] if payloads else None)
        self.setUpdatesEnabled(True)

    def payload(self, row: int):
        it = self.item(row, 0)
        return it.data(PAYLOAD) if it else None

    def fit_height(self, max_rows: int | None = None, extra: int = 0) -> None:
        n = self.rowCount() if max_rows is None else min(self.rowCount(), max_rows)
        self.setFixedHeight(self.horizontalHeader().sizeHint().height() + n * self.row_height + 4 + extra)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if max_rows is None
                                        else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
