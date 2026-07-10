from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import QApplication, QLabel, QWidget

try:
    import qtawesome as qta
except ImportError:  # pragma: no cover - optional UI dependency
    qta = None


class Colors:
    """Design tokens for the dashboard (dark, demo-friendly)."""

    BACKGROUND = "#0c0f14"
    SURFACE = "#12161d"
    PANEL = "#151a22"
    PANEL_ALT = "#1b212b"
    BORDER = "#242c37"
    BORDER_STRONG = "#39434f"
    TEXT = "#e8edf2"
    TEXT_MUTED = "#94a0ad"
    TEXT_SUBTLE = "#68737f"
    PRIMARY = "#31c48d"
    PRIMARY_SOFT = "#173328"
    INFO = "#5aa9e6"
    INFO_SOFT = "#14212e"
    WARNING = "#f0b429"
    WARNING_SOFT = "#2e2513"
    DANGER = "#ef5b6e"
    DANGER_SOFT = "#301820"
    SUCCESS = "#40d698"
    CANVAS = "#0e1218"
    CANVAS_ALT = "#10151c"
    CANVAS_BORDER = "#232d38"
    LIVE = "#40d698"
    STALE = "#f0b429"
    OFFLINE = "#68737f"


ICON_SIZE = QSize(15, 15)
FONT_FAMILY = 'Segoe UI, Inter, "Helvetica Neue", Arial, sans-serif'


APP_STYLESHEET = f"""
QWidget {{
    background: {Colors.BACKGROUND};
    color: {Colors.TEXT};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}

QMainWindow {{
    background: {Colors.BACKGROUND};
}}

QToolTip {{
    background: {Colors.PANEL_ALT};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER_STRONG};
    padding: 5px 8px;
}}

/* ---------- Header ---------- */

QFrame#appHeader {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #151b24, stop:1 #11161d);
    border: 1px solid {Colors.BORDER};
    border-radius: 10px;
}}

QLabel#appTitle {{
    background: transparent;
    color: #ffffff;
    font-size: 19px;
    font-weight: 800;
}}

QLabel#appSubtitle {{
    background: transparent;
    color: {Colors.TEXT_SUBTLE};
    font-size: 11px;
    font-weight: 600;
}}

/* ---------- Chips & status pills ---------- */

QLabel#chip {{
    background: {Colors.PANEL_ALT};
    color: {Colors.TEXT_MUTED};
    border: 1px solid {Colors.BORDER};
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 700;
}}

QLabel#chip[tone="info"] {{
    color: {Colors.INFO};
    background: {Colors.INFO_SOFT};
    border-color: #1e3a52;
}}

QLabel#chip[tone="good"] {{
    color: {Colors.SUCCESS};
    background: {Colors.PRIMARY_SOFT};
    border-color: #1f4a38;
}}

QLabel#chip[tone="warn"] {{
    color: {Colors.WARNING};
    background: {Colors.WARNING_SOFT};
    border-color: #4a3a15;
}}

QLabel#chip[tone="danger"] {{
    color: {Colors.DANGER};
    background: {Colors.DANGER_SOFT};
    border-color: #532431;
}}

QLabel#statusPill {{
    border-radius: 13px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 800;
    color: {Colors.TEXT_MUTED};
    background: {Colors.PANEL_ALT};
    border: 1px solid {Colors.BORDER_STRONG};
}}

QLabel#statusPill[state="disconnected"] {{
    color: {Colors.TEXT_MUTED};
}}

QLabel#statusPill[state="connecting"] {{
    color: {Colors.WARNING};
    background: {Colors.WARNING_SOFT};
    border-color: #4a3a15;
}}

QLabel#statusPill[state="connected"] {{
    color: {Colors.INFO};
    background: {Colors.INFO_SOFT};
    border-color: #1e3a52;
}}

QLabel#statusPill[state="streaming"] {{
    color: #06130d;
    background: {Colors.SUCCESS};
    border-color: {Colors.SUCCESS};
}}

QLabel#statusPill[state="degraded"] {{
    color: #1d1607;
    background: {Colors.WARNING};
    border-color: {Colors.WARNING};
}}

/* ---------- Buttons ---------- */

QPushButton {{
    background: {Colors.PANEL_ALT};
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER_STRONG};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 700;
}}

QPushButton:hover {{
    background: #232c37;
    border-color: #4a5766;
}}

QPushButton:pressed {{
    background: #0f141a;
}}

QPushButton:disabled {{
    color: {Colors.TEXT_SUBTLE};
    background: #141920;
    border-color: #202832;
}}

QPushButton[variant="primary"] {{
    color: #06130d;
    background: {Colors.PRIMARY};
    border-color: {Colors.PRIMARY};
}}

QPushButton[variant="primary"]:hover {{
    background: #43d69f;
    border-color: #43d69f;
}}

QPushButton[variant="primary"]:disabled {{
    color: #6d9384;
    background: #16332a;
    border-color: #204a3b;
}}

QPushButton[variant="danger"] {{
    color: {Colors.DANGER};
    background: {Colors.DANGER_SOFT};
    border-color: #5c2a37;
}}

QPushButton[variant="danger"]:hover {{
    background: #47202b;
    border-color: {Colors.DANGER};
}}

QPushButton[variant="danger"]:disabled {{
    color: #7c545e;
    background: #241419;
    border-color: #3a2029;
}}

QPushButton[variant="ghost"] {{
    color: {Colors.TEXT};
    background: transparent;
    border-color: {Colors.BORDER};
}}

QPushButton[variant="ghost"]:hover {{
    background: {Colors.PANEL_ALT};
}}

/* ---------- Inputs ---------- */

QLineEdit {{
    background: #0f141b;
    color: {Colors.TEXT};
    border: 1px solid {Colors.BORDER};
    border-radius: 7px;
    padding: 7px 9px;
    selection-background-color: #1f4a3b;
}}

QLineEdit:focus {{
    border-color: {Colors.PRIMARY};
}}

/* ---------- Panels ---------- */

QFrame#panel {{
    background: {Colors.PANEL};
    border: 1px solid {Colors.BORDER};
    border-radius: 10px;
}}

QFrame#panel[role="hero"] {{
    background: #131920;
    border-color: #2b3743;
}}

QLabel#panelTitle {{
    color: {Colors.TEXT_MUTED};
    font-size: 11px;
    font-weight: 800;
    background: transparent;
}}

QLabel#panelCaption {{
    color: {Colors.TEXT_SUBTLE};
    font-size: 11px;
    background: transparent;
}}

QLabel#heroValue {{
    color: #ffffff;
    font-size: 38px;
    font-weight: 900;
    background: transparent;
}}

QLabel#heroValue[tone="waiting"] {{
    color: {Colors.TEXT_SUBTLE};
}}

QLabel#heroUnit {{
    color: {Colors.TEXT_MUTED};
    font-size: 14px;
    font-weight: 700;
    background: transparent;
}}

QLabel#objectValue {{
    color: #ffffff;
    font-size: 30px;
    font-weight: 900;
    background: transparent;
}}

QLabel#metricLabel {{
    color: {Colors.TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}

QLabel#metricValue {{
    color: {Colors.TEXT};
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}}

QLabel#metricValue[tone="na"] {{
    color: {Colors.TEXT_SUBTLE};
    font-weight: 600;
}}

QLabel#metricValue[tone="good"] {{
    color: {Colors.SUCCESS};
}}

QLabel#metricValue[tone="warn"] {{
    color: {Colors.WARNING};
}}

QLabel#muted {{
    color: {Colors.TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}

QLabel {{
    background: transparent;
}}

/* ---------- Experiment status badges ---------- */

QLabel#recOn, QLabel#recOff {{
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 800;
}}

QLabel#recOff {{
    color: {Colors.TEXT_MUTED};
    background: {Colors.PANEL_ALT};
    border: 1px solid {Colors.BORDER};
}}

QLabel#recOn {{
    color: #06130d;
    background: {Colors.SUCCESS};
    border: 1px solid {Colors.SUCCESS};
}}

/* ---------- Status bar ---------- */

QFrame#statusBar {{
    background: {Colors.SURFACE};
    border: 1px solid {Colors.BORDER};
    border-radius: 8px;
}}

QLabel#statusDetail {{
    color: {Colors.TEXT_SUBTLE};
    font-size: 11px;
    background: transparent;
}}

QLabel#statusLog {{
    color: {Colors.TEXT_MUTED};
    font-size: 11px;
    background: transparent;
}}

/* ---------- Scroll ---------- */

QScrollArea {{
    background: transparent;
    border: 0;
}}

QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: #29323d;
    border-radius: 4px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background: #3a4653;
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: #29323d;
    border-radius: 4px;
    min-width: 40px;
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QSplitter::handle {{
    background: transparent;
    width: 8px;
}}

QSplitter::handle:hover {{
    background: {Colors.BORDER};
    border-radius: 3px;
}}
"""


def apply_theme(target: QWidget | QApplication | None = None) -> None:
    """Apply the custom dark theme (pure QSS, no external theme package)."""
    app = QApplication.instance()
    styled_target = app or target
    if styled_target is None:
        return
    if isinstance(styled_target, QApplication):
        font = QFont()
        font.setFamilies(["Segoe UI", "Inter", "Helvetica Neue", "Arial"])
        font.setPointSizeF(9.5)
        styled_target.setFont(font)
    styled_target.setStyleSheet(APP_STYLESHEET)


def icon(name: str, color: str = Colors.TEXT, active_color: str = Colors.PRIMARY) -> QIcon:
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color, color_active=active_color)
    except Exception:
        return QIcon()


def make_chip(text: str = "", tone: str = "") -> QLabel:
    """Small rounded status chip used in the header and panels."""
    chip = QLabel(text)
    chip.setObjectName("chip")
    if tone:
        chip.setProperty("tone", tone)
    chip.setAlignment(Qt.AlignCenter)
    return chip


def set_chip(chip: QLabel, text: str, tone: str = "") -> None:
    """Update a chip's text/tone and force a style refresh."""
    chip.setText(text)
    if chip.property("tone") != tone:
        chip.setProperty("tone", tone)
        _repolish(chip)


def set_widget_property(widget: QWidget, name: str, value: object) -> None:
    if widget.property(name) != value:
        widget.setProperty(name, value)
        _repolish(widget)


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def status_color(state: str) -> QColor:
    mapping = {
        "streaming": QColor(Colors.LIVE),
        "connected": QColor(Colors.INFO),
        "connecting": QColor(Colors.WARNING),
        "degraded": QColor(Colors.WARNING),
        "disconnected": QColor(Colors.OFFLINE),
    }
    return mapping.get(state, QColor(Colors.OFFLINE))
