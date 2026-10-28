"""
PyOS — Hybrid OS Simulation
Entry point with Login Screen.
"""

import sys
import os

os.environ["QT_ENABLE_HIGHDPI_SCALING"]  = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

from settings_manager import get_settings
from themes import build_stylesheet


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PyOS")
    app.setApplicationVersion("2.0.0")
    app.setApplicationDisplayName("PyOS")

    sm = get_settings()

    app.setStyleSheet(
        build_stylesheet(sm.get("theme", "dark"), sm.get("accent_color", "#0078d4"))
    )

    font = QFont("Segoe UI", sm.get("font_size", 10))
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)

    from login import LoginWindow
    from main_gui import MainWindow

    login_win = LoginWindow()

    def on_login(user):
        login_win.close()
        window = MainWindow(current_user=user)
        window.show()
        app._main_window = window

    login_win.login_success.connect(on_login)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
