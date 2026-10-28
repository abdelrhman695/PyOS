"""
Theme Engine
Provides complete QSS stylesheets for dark and light themes,
with dynamic accent color substitution.
"""

from PyQt6.QtGui import QColor


def _lighten(hex_color: str, factor: float = 0.3) -> str:
    c = QColor(hex_color)
    h, s, v, a = c.getHsvF()
    v = min(1.0, v + factor)
    c.setHsvF(h, s, v, a)
    return c.name()


def _alpha(hex_color: str, alpha: int = 40) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def build_stylesheet(theme: str = "dark", accent: str = "#0078d4") -> str:
    """Return a complete QSS stylesheet for the given theme and accent color."""
    light_accent = _lighten(accent, 0.15)
    accent_alpha = _alpha(accent, 50)

    if theme == "light":
        return _light(accent, light_accent, accent_alpha)
    return _dark(accent, light_accent, accent_alpha)


def _dark(accent: str, light_accent: str, accent_alpha: str) -> str:
    return f"""
/* ── Global ──────────────────────────────────────────── */
QWidget {{
    background: #1a1b26;
    color: #c0caf5;
    font-size: 12px;
    font-family: 'Segoe UI', 'SF Pro Display', 'Ubuntu', sans-serif;
}}
QMainWindow, QDialog {{ background: #1a1b26; }}

/* ── Buttons ─────────────────────────────────────────── */
QPushButton {{
    background: #24283b;
    color: #c0caf5;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 7px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background: #2d3149;
    border-color: {accent};
}}
QPushButton:pressed  {{ background: {accent_alpha}; }}
QPushButton:disabled {{ color: #414868; background: #1e2030; }}
QPushButton[primary="true"] {{
    background: {accent};
    color: #ffffff;
    border: none;
}}
QPushButton[primary="true"]:hover {{ background: {light_accent}; }}

/* ── Inputs ──────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: #1e2030;
    color: #c0caf5;
    border: 1px solid #414868;
    border-radius: 7px;
    padding: 5px 10px;
    selection-background-color: {accent};
}}
QLineEdit:focus, QTextEdit:focus {{
    border-color: {accent};
}}

/* ── Tables ──────────────────────────────────────────── */
QTableWidget {{
    background: #1e2030;
    color: #c0caf5;
    border: 1px solid #24283b;
    gridline-color: rgba(255,255,255,0.04);
    alternate-background-color: #1a1b26;
}}
QTableWidget::item:selected {{ background: {accent}; color: #ffffff; }}
QHeaderView::section {{
    background: #24283b;
    color: #565f89;
    border: none;
    padding: 6px 8px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
}}

/* ── Progress Bars ───────────────────────────────────── */
QProgressBar {{
    background: #24283b;
    border: none;
    border-radius: 4px;
    height: 8px;
    color: transparent;
    text-align: center;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {accent}, stop:1 {light_accent});
    border-radius: 4px;
}}

/* ── Tabs ────────────────────────────────────────────── */
QTabWidget::pane {{ border: none; background: #1a1b26; }}
QTabBar::tab {{
    background: #24283b;
    color: #565f89;
    padding: 7px 16px;
    margin-right: 2px;
    border-radius: 6px 6px 0 0;
    font-size: 12px;
}}
QTabBar::tab:selected {{ background: {accent}; color: #ffffff; }}
QTabBar::tab:hover:!selected {{ background: #2d3149; color: #c0caf5; }}

/* ── Combo Boxes ─────────────────────────────────────── */
QComboBox {{
    background: #24283b;
    color: #c0caf5;
    border: 1px solid #414868;
    border-radius: 7px;
    padding: 5px 10px;
}}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: #24283b;
    color: #c0caf5;
    border: 1px solid #414868;
    selection-background-color: {accent};
    outline: none;
}}

/* ── Scroll Bars ─────────────────────────────────────── */
QScrollBar:vertical {{
    background: #1e2030;
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #414868;
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 8px; background: #1e2030; border-radius: 4px; }}
QScrollBar::handle:horizontal {{ background: #414868; border-radius: 4px; }}
QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Group Boxes ─────────────────────────────────────── */
QGroupBox {{
    border: 1px solid #24283b;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 8px;
    color: #565f89;
    font-size: 11px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    letter-spacing: 0.5px;
}}

/* ── Checkboxes ──────────────────────────────────────── */
QCheckBox {{ spacing: 8px; color: #c0caf5; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 2px solid #414868;
    border-radius: 5px;
    background: #1e2030;
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url(none);
}}

/* ── Sliders ─────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: #24283b; height: 4px; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {accent}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: #ffffff;
    border: 2px solid {accent};
    width: 16px; height: 16px; margin: -6px 0;
    border-radius: 9px;
}}

/* ── Spin Boxes ──────────────────────────────────────── */
QSpinBox {{
    background: #1e2030;
    color: #c0caf5;
    border: 1px solid #414868;
    border-radius: 7px;
    padding: 4px 8px;
}}
QSpinBox:focus {{ border-color: {accent}; }}

/* ── List Widget ─────────────────────────────────────── */
QListWidget {{
    background: #1e2030;
    color: #c0caf5;
    border: none;
    outline: none;
}}
QListWidget::item {{ padding: 9px 14px; border-radius: 0; }}
QListWidget::item:selected {{ background: {accent}; color: #ffffff; border-radius: 0; }}
QListWidget::item:hover:!selected {{ background: #24283b; }}

/* ── Menu ────────────────────────────────────────────── */
QMenu {{
    background: #1e2030;
    color: #c0caf5;
    border: 1px solid #414868;
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {accent}; color: white; }}

/* ── MDI ─────────────────────────────────────────────── */
QMdiArea {{ background: transparent; border: none; }}
QMdiSubWindow {{
    background: #1a1b26;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 12px;
}}

/* ── Tooltips ────────────────────────────────────────── */
QToolTip {{
    background: #24283b;
    color: #c0caf5;
    border: 1px solid {accent};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 11px;
}}
"""


def _light(accent: str, light_accent: str, accent_alpha: str) -> str:
    return f"""
/* ── Global ──────────────────────────────────────────── */
QWidget {{
    background: #f5f5f7;
    color: #1d1d1f;
    font-size: 12px;
    font-family: 'Segoe UI', 'SF Pro Display', 'Ubuntu', sans-serif;
}}
QMainWindow, QDialog {{ background: #f5f5f7; }}

/* ── Buttons ─────────────────────────────────────────── */
QPushButton {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d1d1d6;
    border-radius: 7px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background: #f0f0f5;
    border-color: {accent};
}}
QPushButton:pressed  {{ background: {accent_alpha}; }}
QPushButton:disabled {{ color: #aeaeb2; background: #e5e5ea; }}
QPushButton[primary="true"] {{
    background: {accent};
    color: #ffffff;
    border: none;
}}
QPushButton[primary="true"]:hover {{ background: {light_accent}; }}

/* ── Inputs ──────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d1d1d6;
    border-radius: 7px;
    padding: 5px 10px;
    selection-background-color: {accent};
}}
QLineEdit:focus, QTextEdit:focus {{ border-color: {accent}; }}

/* ── Tables ──────────────────────────────────────────── */
QTableWidget {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid #e5e5ea;
    gridline-color: #f0f0f5;
    alternate-background-color: #f9f9fb;
}}
QTableWidget::item:selected {{ background: {accent}; color: #ffffff; }}
QHeaderView::section {{
    background: #f0f0f5;
    color: #6e6e73;
    border: none;
    padding: 6px 8px;
    font-weight: 600;
    font-size: 11px;
}}

/* ── Progress Bars ───────────────────────────────────── */
QProgressBar {{
    background: #e5e5ea;
    border: none;
    border-radius: 4px;
    height: 8px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {accent}, stop:1 {light_accent});
    border-radius: 4px;
}}

/* ── Tabs ────────────────────────────────────────────── */
QTabWidget::pane {{ border: none; background: #f5f5f7; }}
QTabBar::tab {{
    background: #e5e5ea;
    color: #6e6e73;
    padding: 7px 16px;
    margin-right: 2px;
    border-radius: 6px 6px 0 0;
}}
QTabBar::tab:selected {{ background: {accent}; color: #ffffff; }}
QTabBar::tab:hover:!selected {{ background: #d1d1d6; color: #1d1d1f; }}

/* ── Combo Boxes ─────────────────────────────────────── */
QComboBox {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d1d1d6;
    border-radius: 7px;
    padding: 5px 10px;
}}
QComboBox:focus {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d1d1d6;
    selection-background-color: {accent};
    selection-color: white;
    outline: none;
}}

/* ── Scroll Bars ─────────────────────────────────────── */
QScrollBar:vertical {{
    background: #f0f0f5;
    width: 8px; margin: 0; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #c7c7cc; min-height: 30px; border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 8px; background: #f0f0f5; border-radius: 4px; }}
QScrollBar::handle:horizontal {{ background: #c7c7cc; border-radius: 4px; }}
QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Group Boxes ─────────────────────────────────────── */
QGroupBox {{
    border: 1px solid #e5e5ea;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 8px;
    color: #6e6e73;
    font-size: 11px;
    font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}

/* ── Checkboxes ──────────────────────────────────────── */
QCheckBox {{ spacing: 8px; color: #1d1d1f; }}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 2px solid #c7c7cc;
    border-radius: 5px;
    background: #ffffff;
}}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}

/* ── Sliders ─────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: #e5e5ea; height: 4px; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #ffffff;
    border: 2px solid {accent};
    width: 16px; height: 16px; margin: -6px 0; border-radius: 9px;
}}

/* ── Spin Boxes ──────────────────────────────────────── */
QSpinBox {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d1d1d6;
    border-radius: 7px;
    padding: 4px 8px;
}}
QSpinBox:focus {{ border-color: {accent}; }}

/* ── List Widget ─────────────────────────────────────── */
QListWidget {{
    background: #ffffff;
    color: #1d1d1f;
    border: none;
    outline: none;
}}
QListWidget::item {{ padding: 9px 14px; }}
QListWidget::item:selected {{ background: {accent}; color: #ffffff; }}
QListWidget::item:hover:!selected {{ background: #f0f0f5; }}

/* ── Menu ────────────────────────────────────────────── */
QMenu {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid #d1d1d6;
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {accent}; color: white; }}

/* ── MDI ─────────────────────────────────────────────── */
QMdiArea {{ background: transparent; border: none; }}
QMdiSubWindow {{
    background: #f5f5f7;
    border: 1px solid #d1d1d6;
    border-radius: 12px;
}}

/* ── Tooltips ────────────────────────────────────────── */
QToolTip {{
    background: #ffffff;
    color: #1d1d1f;
    border: 1px solid {accent};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 11px;
}}
"""
