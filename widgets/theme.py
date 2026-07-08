from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QWidget

try:
    import qdarktheme
except ImportError:  # pragma: no cover - optional UI dependency
    qdarktheme = None

try:
    import qtawesome as qta
except ImportError:  # pragma: no cover - optional UI dependency
    qta = None


class Colors:
    BACKGROUND = "#0b0f12"
    SURFACE = "#11161a"
    PANEL = "#171d22"
    PANEL_ALT = "#1d242a"
    BORDER = "#2a343c"
    BORDER_STRONG = "#3d4b55"
    TEXT = "#edf4f7"
    TEXT_MUTED = "#95a4ae"
    TEXT_SUBTLE = "#6f7f89"
    PRIMARY = "#2fbf8f"
    PRIMARY_DARK = "#14664f"
    INFO = "#70d6ff"
    WARNING = "#ffcf33"
    DANGER = "#e05263"
    SUCCESS = "#5ee2a0"
    CANVAS = "#0f151b"
    CANVAS_ALT = "#121a21"
    CANVAS_BORDER = "#293846"


ICON_SIZE = QSize(16, 16)


APP_STYLESHEET = f"""
QWidget {{
    background: {Colors.BACKGROUND};
    color: {Colors.TEXT};
    font-family: Inter, Segoe UI, Arial, sans-serif;
    font-size: 14px;
}}

QMainWindow {{
    background: {Colors.BACKGROUND};
}}

QFrame#appHeader {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {Colors.SURFACE}, stop:1 #131c1c);
    border: 1px solid {Colors.BORDER};
    border-radius: 8px;
}}

QLabel#appTitle {{
    background: transparent;
    color: #ffffff;
    font-size: 24px;
    font-weight: 800;
}}

QLabel {{
    background: transparent;
    color: #cfd9df;
}}

QLabel#appSubtitle,
QLabel#sectionLabel,
QLabel#muted {{
    background: transparent;
    color: {Colors.TEXT_MUTED};
    font-size: 12px;
}}

QLabel#sectionLabel {{
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
}}

QLabel#modeBadge,
QLabel#recOn,
QLabel#recOff {{
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 800;
}}

QLabel#modeBadge[state="idle"],
QLabel#recOff {{
    color: {Colors.TEXT_MUTED};
    background: {Colors.PANEL_ALT};
    border: 1px solid {Colors.BORDER};
}}

QLabel#modeBadge[state="active"],
QLabel#recOn {{
    color: #06100c;
    background: {Colors.SUCCESS};
    border: 1px solid {Colors.SUCCESS};
}}

QLabel#modeBadge[state="warning"] {{
    color: #160c0f;
    background: {Colors.WARNING};
    border: 1px solid {Colors.WARNING};
}}

QFrame#commandBar {{
    background: transparent;
}}

QPushButton {{
    background: {Colors.PANEL_ALT};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER_STRONG};
    border-radius: 7px;
    padding: 8px 12px;
    min-height: 18px;
    font-weight: 700;
}}

QPushButton:hover {{
    background: #263039;
    border-color: #53626d;
}}

QPushButton:pressed {{
    background: #10171b;
}}

QPushButton:disabled {{
    color: {Colors.TEXT_SUBTLE};
    background: #12171b;
    border-color: #222b31;
}}

QPushButton[variant="primary"] {{
    color: #06100c;
    background: {Colors.PRIMARY};
    border-color: {Colors.PRIMARY};
}}

QPushButton[variant="primary"]:hover {{
    background: #45d5a7;
    border-color: #45d5a7;
}}

QPushButton[variant="danger"] {{
    color: #fff6f7;
    background: #6f2633;
    border-color: {Colors.DANGER};
}}

QPushButton[variant="danger"]:hover {{
    background: #8a3040;
}}

QPushButton[variant="danger"]:disabled {{
    color: #dca9b0;
    background: #3a2028;
    border-color: #5a303b;
}}

QPushButton[variant="primary"]:disabled {{
    color: #7da899;
    background: #17332b;
    border-color: #245547;
}}

QPushButton[variant="ghost"] {{
    color: {Colors.TEXT};
    background: transparent;
    border-color: {Colors.BORDER};
}}

QPushButton[variant="ghost"]:hover {{
    background: {Colors.PANEL_ALT};
}}

QLineEdit {{
    background: #10161a;
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
    border-radius: 6px;
    padding: 8px 9px;
    selection-background-color: {Colors.PRIMARY_DARK};
}}

QLineEdit:focus {{
    border-color: {Colors.PRIMARY};
}}

QFrame#panel {{
    background: {Colors.PANEL};
    border: 1px solid {Colors.BORDER};
    border-radius: 8px;
}}

QFrame#panel[role="hero"] {{
    background: #141b20;
    border-color: #33434d;
}}

QFrame#panel[role="heart"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #151d1e, stop:1 #171922);
    border-color: #345144;
}}

QLabel#panelTitle {{
    color: #ffffff;
    font-size: 16px;
    font-weight: 800;
}}

QLabel#bpmValue {{
    color: {Colors.WARNING};
    font-size: 40px;
    font-weight: 900;
}}

QLabel#objectValue {{
    color: #ffffff;
    font-size: 34px;
    font-weight: 900;
}}

QCheckBox {{
    color: #cfdae0;
    spacing: 8px;
    min-height: 24px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid {Colors.BORDER_STRONG};
    background: #10161a;
}}

QCheckBox::indicator:hover {{
    border-color: {Colors.PRIMARY};
}}

QCheckBox::indicator:checked {{
    background: {Colors.PRIMARY};
    border-color: {Colors.PRIMARY};
}}

QScrollArea {{
    background: transparent;
    border: 0;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: #2c3740;
    border-radius: 5px;
    min-height: 44px;
}}

QScrollBar::handle:vertical:hover {{
    background: #3e4b55;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QSplitter::handle {{
    background: transparent;
}}

QSplitter::handle:hover {{
    background: {Colors.BORDER};
}}

QLabel#statusLine {{
    color: #cdd7dd;
    background: {Colors.SURFACE};
    border: 1px solid {Colors.BORDER};
    border-radius: 7px;
    padding: 8px 10px;
}}
"""


def apply_theme(target: QWidget | QApplication | None = None) -> None:
    app = QApplication.instance()
    if app is not None and qdarktheme is not None:
        try:
            qdarktheme.setup_theme(
                "dark",
                custom_colors={"primary": Colors.PRIMARY},
                additional_qss=APP_STYLESHEET,
            )
            return
        except Exception:
            pass

    styled_target = app or target
    if styled_target is not None:
        styled_target.setStyleSheet(APP_STYLESHEET)


def icon(name: str, color: str = Colors.TEXT, active_color: str = Colors.PRIMARY) -> QIcon:
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color, color_active=active_color)
    except Exception:
        return QIcon()


def add_card_shadow(widget: QWidget) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(28)
    effect.setOffset(0, 8)
    effect.setColor(QColor(0, 0, 0, 95))
    widget.setGraphicsEffect(effect)
