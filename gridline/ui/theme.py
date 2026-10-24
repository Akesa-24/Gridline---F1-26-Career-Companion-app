"""Colours, fonts and the application stylesheet."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent.parent / "assets"


class P:
    """Palette. Deep navy base, electric blue accent, F1 timing colours."""
    bg0 = "#060B17"        # sidebar / chrome
    bg1 = "#0A1224"        # page canvas
    card = "#0F1A31"
    card2 = "#14223D"      # raised / hover
    card3 = "#1A2B4B"
    line = "#1C2C4A"
    line2 = "#28406A"
    text = "#E7EDF8"
    text2 = "#9CABC8"
    text3 = "#5F7198"
    accent = "#3D8BFF"
    accent2 = "#7DB4FF"
    accent_dim = "#17325F"
    ok = "#35D49A"
    warn = "#FFB547"
    bad = "#FF5C70"
    purple = "#B47BFF"
    gold = "#F7C948"
    silver = "#C3CEDF"
    bronze = "#D9925A"


FONT_UI = "Titillium Web"
FONT_MONO = "JetBrains Mono"


def load_fonts() -> None:
    global FONT_UI, FONT_MONO
    fams = {}
    for f in (ASSETS / "fonts").glob("*.ttf"):
        fid = QFontDatabase.addApplicationFont(str(f))
        for fam in QFontDatabase.applicationFontFamilies(fid):
            fams[fam] = True
    if "Titillium Web" not in fams:
        FONT_UI = "Segoe UI"
    if "JetBrains Mono" not in fams:
        FONT_MONO = "Consolas"


def font(size: float = 10, weight: QFont.Weight = QFont.Weight.Normal, mono: bool = False) -> QFont:
    f = QFont(FONT_MONO if mono else FONT_UI)
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def qc(hex_: str, alpha: int | None = None) -> QColor:
    c = QColor(hex_)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def apply(app: QApplication) -> None:
    load_fonts()
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, qc(P.bg1))
    pal.setColor(QPalette.ColorRole.WindowText, qc(P.text))
    pal.setColor(QPalette.ColorRole.Base, qc(P.card))
    pal.setColor(QPalette.ColorRole.AlternateBase, qc(P.card2))
    pal.setColor(QPalette.ColorRole.Text, qc(P.text))
    pal.setColor(QPalette.ColorRole.Button, qc(P.card2))
    pal.setColor(QPalette.ColorRole.ButtonText, qc(P.text))
    pal.setColor(QPalette.ColorRole.Highlight, qc(P.accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, qc("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, qc(P.card3))
    pal.setColor(QPalette.ColorRole.ToolTipText, qc(P.text))
    pal.setColor(QPalette.ColorRole.PlaceholderText, qc(P.text3))
    app.setPalette(pal)
    app.setFont(font(10))
    app.setStyleSheet(STYLESHEET)


STYLESHEET = f"""
* {{ outline: 0; }}
QWidget {{ color: {P.text}; font-family: "{FONT_UI}"; }}
QMainWindow, #Canvas {{ background: {P.bg1}; }}
#Sidebar {{ background: {P.bg0}; border-right: 1px solid {P.line}; }}

QLabel[role="title"] {{ font-size: 21pt; font-weight: 600; color: {P.text}; }}
QLabel[role="subtitle"] {{ font-size: 10pt; color: {P.text2}; }}
QLabel[role="section"] {{ font-size: 8.5pt; font-weight: 700; color: {P.text3};
    letter-spacing: 1.5px; text-transform: uppercase; }}
QLabel[role="muted"] {{ color: {P.text2}; }}
QLabel[role="faint"] {{ color: {P.text3}; }}
QLabel[role="big"] {{ font-size: 26pt; font-weight: 700; }}
QLabel[role="metric"] {{ font-size: 17pt; font-weight: 700; }}

#Card {{ background: {P.card}; border: 1px solid {P.line}; border-radius: 10px; }}
#CardFlat {{ background: {P.card}; border-radius: 10px; }}

QPushButton {{
    background: {P.card2}; border: 1px solid {P.line2}; border-radius: 7px;
    padding: 7px 16px; font-weight: 600; color: {P.text};
}}
QPushButton:hover {{ background: {P.card3}; border-color: {P.accent_dim}; }}
QPushButton:pressed {{ background: {P.line}; }}
QPushButton:disabled {{ color: {P.text3}; border-color: {P.line}; background: {P.card}; }}
QPushButton[kind="primary"] {{ background: {P.accent}; border: 1px solid {P.accent}; color: #FFFFFF; }}
QPushButton[kind="primary"]:hover {{ background: #5299FF; }}
QPushButton[kind="primary"]:disabled {{ background: {P.accent_dim}; border-color: {P.accent_dim}; color: {P.text2}; }}
QPushButton[kind="danger"] {{ background: transparent; border: 1px solid #5A2232; color: {P.bad}; }}
QPushButton[kind="danger"]:hover {{ background: #2A1220; }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {P.text2}; }}
QPushButton[kind="ghost"]:hover {{ color: {P.text}; background: {P.card2}; }}
QPushButton[kind="seg"] {{ background: transparent; border: none; border-radius: 6px;
    padding: 6px 14px; color: {P.text2}; }}
QPushButton[kind="seg"]:checked {{ background: {P.card3}; color: {P.text}; }}

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {P.bg0}; border: 1px solid {P.line2}; border-radius: 7px;
    padding: 7px 10px; selection-background-color: {P.accent};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {P.accent}; }}
QLineEdit[mono="true"], QPlainTextEdit[mono="true"] {{ font-family: "{FONT_MONO}"; font-size: 9pt; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {P.card2}; border: 1px solid {P.line2};
    selection-background-color: {P.accent_dim}; padding: 4px; }}
QSpinBox {{ padding: 6px 10px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: 8px; color: {P.text}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {P.line2}; background: {P.bg0}; }}
QCheckBox::indicator:checked {{ background: {P.accent}; border-color: {P.accent}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {P.line2}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {P.text3}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {P.line2}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ width: 0; height: 0; background: none; }}

QTableView {{ background: transparent; border: none; gridline-color: transparent;
    selection-background-color: {P.card2}; selection-color: {P.text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {P.text3}; border: none;
    border-bottom: 1px solid {P.line}; padding: 6px 8px; font-size: 8pt; font-weight: 700; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QListWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border-radius: 6px; padding: 6px 8px; }}
QListWidget::item:selected {{ background: {P.card2}; }}
QListWidget::item:hover {{ background: {P.card}; }}

QToolTip {{ background: {P.card3}; color: {P.text}; border: 1px solid {P.line2}; padding: 6px; border-radius: 6px; }}
QMenu {{ background: {P.card2}; border: 1px solid {P.line2}; padding: 6px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {P.accent_dim}; }}
QDialog {{ background: {P.bg1}; }}
QTabBar::tab {{ background: transparent; color: {P.text2}; padding: 8px 14px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {P.text}; border-bottom-color: {P.accent}; }}
QTabWidget::pane {{ border: none; }}
"""
