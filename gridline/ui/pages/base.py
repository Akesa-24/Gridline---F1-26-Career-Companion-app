from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..widgets.common import PageHeader


class Page(QWidget):
    """Scrollable page with a header. Subclasses fill `self.body` and implement refresh()."""

    title = ""
    scroll = True

    def __init__(self, core, title: str | None = None):
        super().__init__()
        self.core = core
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = PageHeader(title or self.title)
        inner = QWidget()
        inner.setObjectName("Canvas")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(32, 26, 32, 28)
        self.body.setSpacing(18)
        self.body.addWidget(self.header)
        if self.scroll:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            sa.setWidget(inner)
            outer.addWidget(sa)
        else:
            outer.addWidget(inner)

    def refresh(self, state) -> None:  # pragma: no cover - overridden
        pass
