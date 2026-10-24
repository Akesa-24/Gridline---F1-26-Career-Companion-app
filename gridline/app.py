"""Application entry point."""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from .core import AppCore
    from .ui import theme
    from .ui.main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Gridline")
    app.setOrganizationName("Gridline")
    theme.apply(app)

    core = AppCore()
    win = MainWindow(core)
    core.start()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
