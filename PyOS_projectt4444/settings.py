"""
Settings Panel
Full-featured settings UI with:
  - Appearance (theme, accent color, background, font size, dock position)
  - Terminal config
  - Performance tuning
  - Network settings
  - About page
All changes persist instantly via SettingsManager (JSON storage).
"""

import os
import platform

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap, QPainter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QCheckBox, QGroupBox, QListWidget,
    QListWidgetItem, QStackedWidget, QScrollArea, QFrame,
    QColorDialog, QFileDialog, QSpinBox, QLineEdit,
    QButtonGroup, QRadioButton, QSizePolicy
)

from settings_manager import SettingsManager, get_settings
from animated_background import BACKGROUND_STYLES


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet("border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 4px 0;")
    return f


def _section(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet("font-size:13px; font-weight:700; padding-bottom:2px;")
    return l


def _note(text: str) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet("font-size:11px; color: #6e7681;")
    l.setWordWrap(True)
    return l


def _row_layout(label: str, widget: QWidget, stretch: bool = True) -> QHBoxLayout:
    row = QHBoxLayout()
    lbl = QLabel(label)
    lbl.setStyleSheet("font-size:12px;")
    lbl.setFixedWidth(180)
    row.addWidget(lbl)
    row.addWidget(widget)
    if stretch:
        row.addStretch()
    return row


def _color_swatch(hex_color: str, size: int = 22) -> QPixmap:
    px = QPixmap(size, size)
    px.fill(QColor(hex_color))
    p = QPainter(px)
    p.setPen(QColor(0, 0, 0, 60))
    p.drawRect(0, 0, size - 1, size - 1)
    p.end()
    return px


class AppearancePage(QWidget):
    def __init__(self, sm: SettingsManager, parent=None):
        super().__init__(parent)
        self._sm = sm
        self._build()

    def _build(self):
        outer = QScrollArea(self)
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lay.addWidget(_section("Theme"))
        lay.addWidget(_sep())

        theme_row = QHBoxLayout()
        for label, value in [("🌑  Dark", "dark"), ("☀️  Light", "light")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(self._sm.get("theme") == value)
            btn.setFixedHeight(36)
            btn.setStyleSheet(
                "QPushButton { border-radius:8px; padding: 6px 20px; font-size:12px; }"
                "QPushButton:checked { background: #1f6feb; color: white; border: none; }"
            )
            val = value
            btn.clicked.connect(lambda _, v=val: self._sm.set("theme", v))
            theme_row.addWidget(btn)
        theme_row.addStretch()
        lay.addLayout(theme_row)
        lay.addSpacing(6)

        lay.addWidget(_section("Accent Color"))
        lay.addWidget(_sep())

        presets = ["#0078d4", "#2ea043", "#f0ad4e", "#e53935",
                   "#8e24aa", "#00acc1", "#f06292", "#ff7043"]
        accent_row = QHBoxLayout()
        for hex_c in presets:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setToolTip(hex_c)
            btn.setStyleSheet(
                f"QPushButton {{ background: {hex_c}; border-radius: 14px;"
                "border: 2px solid transparent; }}"
                f"QPushButton:hover {{ border-color: white; }}"
            )
            hc = hex_c
            btn.clicked.connect(lambda _, c=hc: self._sm.set("accent_color", c))
            accent_row.addWidget(btn)

        custom_btn = QPushButton("Custom…")
        custom_btn.setFixedHeight(28)
        custom_btn.clicked.connect(self._pick_accent)
        accent_row.addWidget(custom_btn)
        accent_row.addStretch()
        lay.addLayout(accent_row)
        lay.addSpacing(6)

        lay.addWidget(_section("Background"))
        lay.addWidget(_sep())

        bg_combo = QComboBox()
        bg_combo.addItems(["(Animated)"] + BACKGROUND_STYLES)
        current_img = self._sm.get("background_image", "")
        current_style = self._sm.get("background_style", "Aurora")
        bg_combo.setCurrentText(current_style if not current_img else "(Animated)")
        bg_combo.currentTextChanged.connect(self._on_bg_style)
        lay.addLayout(_row_layout("Animated Style", bg_combo))

        img_row = QHBoxLayout()
        self._img_lbl = QLabel(
            os.path.basename(current_img) if current_img else "No image selected"
        )
        self._img_lbl.setStyleSheet("font-size:11px; color:#6e7681;")
        img_btn = QPushButton("Browse Image…")
        img_btn.clicked.connect(self._pick_image)
        img_clear = QPushButton("Clear")
        img_clear.clicked.connect(self._clear_image)
        img_row.addWidget(QLabel("Wallpaper Image"))
        img_row.addStretch()
        img_row.addWidget(self._img_lbl)
        img_row.addWidget(img_btn)
        img_row.addWidget(img_clear)
        lay.addLayout(img_row)
        lay.addWidget(_note("Image takes priority over the animated background."))
        lay.addSpacing(6)

        lay.addWidget(_section("Animations"))
        lay.addWidget(_sep())
        anim_chk = QCheckBox("Enable desktop animations (Aurora, Matrix, etc.)")
        anim_chk.setChecked(self._sm.get("animations_enabled", True))
        anim_chk.toggled.connect(lambda v: self._sm.set("animations_enabled", v))
        lay.addWidget(anim_chk)
        lay.addSpacing(6)

        lay.addWidget(_section("Font Size"))
        lay.addWidget(_sep())
        font_row = QHBoxLayout()
        font_sl = QSlider(Qt.Orientation.Horizontal)
        font_sl.setRange(8, 18)
        font_sl.setValue(self._sm.get("font_size", 10))
        self._font_val = QLabel(f"{font_sl.value()} pt")
        self._font_val.setFixedWidth(40)
        font_sl.valueChanged.connect(lambda v: (
            self._font_val.setText(f"{v} pt"),
            self._sm.set("font_size", v)
        ))
        font_row.addWidget(QLabel("Size"))
        font_row.addWidget(font_sl, 1)
        font_row.addWidget(self._font_val)
        lay.addLayout(font_row)
        lay.addSpacing(6)

        lay.addWidget(_section("Dock"))
        lay.addWidget(_sep())
        dock_combo = QComboBox()
        dock_combo.addItems(["bottom", "top"])
        dock_combo.setCurrentText(self._sm.get("dock_position", "bottom"))
        dock_combo.currentTextChanged.connect(lambda v: self._sm.set("dock_position", v))
        lay.addLayout(_row_layout("Position", dock_combo))

        lay.addStretch()
        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(outer)
        outer.setWidget(content)

    def _on_bg_style(self, style: str):
        if style == "(Animated)":
            return
        self._sm.set("background_style", style)

    def _pick_accent(self):
        current = QColor(self._sm.get("accent_color", "#0078d4"))
        color = QColorDialog.getColor(current, self, "Choose Accent Color")
        if color.isValid():
            self._sm.set("accent_color", color.name())

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Wallpaper", os.path.expanduser("~"),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"
        )
        if path:
            self._sm.set("background_image", path)
            self._img_lbl.setText(os.path.basename(path))

    def _clear_image(self):
        self._sm.set("background_image", "")
        self._img_lbl.setText("No image selected")


class TerminalPage(QWidget):
    def __init__(self, sm: SettingsManager, parent=None):
        super().__init__(parent)
        self._sm = sm
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lay.addWidget(_section("Shell Configuration"))
        lay.addWidget(_sep())

        default_shell = "/bin/bash" if platform.system() != "Windows" else "powershell"
        shell_edit = QLineEdit()
        shell_edit.setPlaceholderText(f"Auto ({default_shell})")
        shell_edit.setText(self._sm.get("terminal_shell", ""))
        shell_edit.textChanged.connect(lambda v: self._sm.set("terminal_shell", v))
        lay.addLayout(_row_layout("Custom Shell", shell_edit, stretch=False))
        lay.addWidget(_note("Leave blank to use the system default shell."))

        lay.addSpacing(10)
        lay.addWidget(_section("Tips"))
        lay.addWidget(_sep())
        tips = [
            "↑ / ↓  — Navigate command history",
            "Ctrl+C  — Interrupt running command",
            "cd ..  — Navigate up one directory",
            "clear  — Clear the terminal output",
            "Press + in the tab bar to open a new terminal tab",
        ]
        for tip in tips:
            lbl = QLabel(f"  •  {tip}")
            lbl.setStyleSheet("font-size:12px; color: #6e7681;")
            lay.addWidget(lbl)
        lay.addStretch()


class PerformancePage(QWidget):
    def __init__(self, sm: SettingsManager, parent=None):
        super().__init__(parent)
        self._sm = sm
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lay.addWidget(_section("System Monitoring"))
        lay.addWidget(_sep())

        spin = QSpinBox()
        spin.setRange(500, 10000)
        spin.setSingleStep(500)
        spin.setSuffix(" ms")
        spin.setValue(self._sm.get("monitor_interval_ms", 2000))
        spin.valueChanged.connect(lambda v: self._sm.set("monitor_interval_ms", v))
        lay.addLayout(_row_layout("Poll Interval", spin))
        lay.addWidget(_note("Lower = more real-time. Higher = less CPU overhead."))

        lay.addSpacing(10)
        lay.addWidget(_section("Auto-Optimization"))
        lay.addWidget(_sep())

        chk = QCheckBox("Reduce animation FPS when CPU usage > 80%")
        chk.setChecked(self._sm.get("auto_optimize", False))
        chk.toggled.connect(lambda v: self._sm.set("auto_optimize", v))
        lay.addWidget(chk)
        lay.addWidget(_note(
            "When enabled, the background animation frame rate drops to 10 fps "
            "during heavy CPU load to reduce overhead."
        ))
        lay.addStretch()


class NetworkPage(QWidget):
    def __init__(self, sm: SettingsManager, parent=None):
        super().__init__(parent)
        self._sm = sm
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        lay.addWidget(_section("Network Scanner"))
        lay.addWidget(_sep())

        spin = QSpinBox()
        spin.setRange(10, 300)
        spin.setSingleStep(10)
        spin.setSuffix(" s")
        spin.setValue(self._sm.get("network_scan_interval_s", 30))
        spin.valueChanged.connect(lambda v: self._sm.set("network_scan_interval_s", v))
        lay.addLayout(_row_layout("Auto-scan Interval", spin))

        lay.addSpacing(10)
        lay.addWidget(_section("Wi-Fi Requirements"))
        lay.addWidget(_sep())

        reqs = {
            "Linux":   "nmcli (NetworkManager)",
            "macOS":   "airport framework",
            "Windows": "netsh wlan",
        }
        for os_name, tool in reqs.items():
            row = QHBoxLayout()
            k = QLabel(f"  {os_name}")
            k.setStyleSheet("font-size:12px; font-weight:600;")
            k.setFixedWidth(80)
            v = QLabel(tool)
            v.setStyleSheet("font-size:12px; color:#6e7681;")
            row.addWidget(k)
            row.addWidget(v)
            row.addStretch()
            lay.addLayout(row)
        lay.addStretch()


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        title = QLabel("PyOS")
        title.setStyleSheet("font-size:28px; font-weight:700; letter-spacing:-1px;")
        lay.addWidget(title)
        lay.addWidget(QLabel("Hybrid Operating System Simulation"))
        lay.addWidget(_sep())

        info = [
            ("Version",    "2.0.0"),
            ("Python",     platform.python_version()),
            ("Platform",   f"{platform.system()} {platform.release()}"),
            ("Machine",    platform.machine()),
            ("Processor",  platform.processor() or "Unknown"),
            ("Config dir", os.path.expanduser("~/.pyos")),
        ]
        for key, val in info:
            row = QHBoxLayout()
            k = QLabel(key)
            k.setStyleSheet("font-size:12px; color:#6e7681;")
            k.setFixedWidth(110)
            v = QLabel(val)
            v.setStyleSheet("font-size:12px;")
            row.addWidget(k)
            row.addWidget(v)
            row.addStretch()
            lay.addLayout(row)

        lay.addStretch()
        footer = QLabel("Educational Python Project — Not a real operating system")
        footer.setStyleSheet("font-size:10px; color:#414868;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(footer)


class SettingsWidget(QWidget):
    """
    Full settings panel with sidebar navigation.
    All changes are applied instantly and persisted to ~/.pyos/settings.json.
    """

    SECTIONS = [
        ("🎨   Appearance",  AppearancePage),
        ("💻   Terminal",    TerminalPage),
        ("⚡   Performance", PerformancePage),
        ("📡   Network",     NetworkPage),
        ("ℹ️    About",       AboutPage),
    ]

    def __init__(self, sm: SettingsManager = None, parent=None):
        super().__init__(parent)
        self._sm = sm or get_settings()
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QListWidget()
        sidebar.setFixedWidth(175)
        sidebar.setStyleSheet(
            "QListWidget { border: none; border-right: 1px solid rgba(255,255,255,0.07);"
            "background: transparent; outline: none; font-size:12px; }"
            "QListWidget::item { padding: 11px 18px; }"
        )
        for label, _ in self.SECTIONS:
            sidebar.addItem(label)
        sidebar.setCurrentRow(0)
        layout.addWidget(sidebar)

        self._stack = QStackedWidget()
        for _, PageClass in self.SECTIONS:
            if PageClass == AboutPage:
                page = PageClass()
            else:
                page = PageClass(self._sm)
            self._stack.addWidget(page)
        layout.addWidget(self._stack, 1)

        sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
