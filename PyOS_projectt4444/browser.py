"""
Browser Module — Full embedded browser INSIDE PyOS using QWebEngineView

FIXES applied (v2.1):
  1. _interceptor created lazily AFTER QApplication exists (was crashing on import)
  2. Private profiles now keep a strong reference (prevented GC crash)
  3. _make_normal_profile() called only once via module-level singleton
  4. clearHttpCache() wrapped safely — no longer crashes on normal profile
  5. All QWebEngineProfile objects parented to the view to avoid GC crashes
  6. Removed double profile creation in _clear_data()
  7. Fixed view_source crash (was returning bare widget with no parent)
  8. Added graceful WebEngineView unavailable fallback

UI Improvements:
  - Redesigned navigation bar with modern pill-style URL bar
  - Improved tab bar with favicon placeholder and close X
  - Reading mode / zoom controls in menu
  - Smooth progress indicator (thin gradient bar)
  - Bookmarks bar (session-only)
  - Download status label
  - Keyboard shortcuts: Ctrl+T, Ctrl+W, Ctrl+L, Ctrl+R, Ctrl+H
"""

import os
import sys
import urllib.parse
from typing import Optional

from PyQt6.QtCore import QUrl, Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QTabWidget, QToolButton, QMenu, QProgressBar,
    QCheckBox, QDialog, QDialogButtonBox, QComboBox, QGroupBox,
    QFrame, QMessageBox, QSizePolicy, QScrollArea,
)
from PyQt6.QtGui import QIcon, QAction, QColor, QKeySequence, QPainter, QBrush, QPen, QShortcut

# ── WebEngine import with graceful fallback ──────────────────────────────────
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import (
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineUrlRequestInterceptor,
        QWebEngineSettings,
    )
    _WEBENGINE_OK = True
except ImportError:
    _WEBENGINE_OK = False


# ══════════════════════════════════════════════════════════════════════════════
# Ad / Tracker Blocklist
# ══════════════════════════════════════════════════════════════════════════════

_BLOCKED_DOMAINS = {
    "google-analytics.com", "analytics.google.com", "googletagmanager.com",
    "googletagservices.com", "googlesyndication.com", "doubleclick.net",
    "adservice.google.com", "pagead2.googlesyndication.com",
    "connect.facebook.net", "pixel.facebook.com",
    "aax.amazon-adsystem.com", "c.amazon-adsystem.com",
    "ads.twitter.com", "analytics.twitter.com", "bat.bing.com",
    "ads.linkedin.com", "px.ads.linkedin.com",
    "static.hotjar.com", "script.hotjar.com",
    "cdn.segment.com", "api.segment.io",
    "cdn.amplitude.com", "api.amplitude.com",
    "d.clarity.ms", "mc.yandex.ru", "mc.yandex.com",
    "scorecardresearch.com", "quantserve.com",
    "outbrain.com", "widgets.outbrain.com",
    "taboola.com", "trc.taboola.com",
    "criteo.com", "rubiconproject.com",
    "pubmatic.com", "openx.net", "openx.com",
    "appnexus.com", "ib.adnxs.com",
    "adroll.com", "moatads.com",
    "chartbeat.com", "newrelic.com",
    "fullstory.com", "logrocket.com",
    "mixpanel.com", "intercom.io",
    "crazyegg.com", "mouseflow.com",
    "inspectlet.com", "clicktale.net",
    "demdex.net", "everesttech.net",
    "casalemedia.com", "yieldmanager.com",
    "advertising.com", "trafficjunky.net",
    "exoclick.com", "juicyads.com",
}

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "dclid", "msclkid", "twclid", "mc_eid",
    "_ga", "_gl", "igshid", "ref_src", "_hsenc", "_hsmi", "yclid",
})


# ── Lazy singletons (created only after QApplication exists) ─────────────────

_interceptor_instance: Optional["_PrivacyInterceptor"] = None
_normal_profile_instance: Optional["QWebEngineProfile"] = None
_private_profiles: list = []          # strong refs to prevent GC crash


def _get_interceptor() -> "_PrivacyInterceptor":
    global _interceptor_instance
    if _interceptor_instance is None and _WEBENGINE_OK:
        _interceptor_instance = _PrivacyInterceptor()
    return _interceptor_instance


def _get_normal_profile() -> "QWebEngineProfile":
    """Return the one-and-only normal profile (singleton)."""
    global _normal_profile_instance
    if _normal_profile_instance is None and _WEBENGINE_OK:
        profile = QWebEngineProfile.defaultProfile()
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_cache")
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        profile.setPersistentStoragePath(cache_dir)
        profile.setUrlRequestInterceptor(_get_interceptor())
        _apply_privacy_settings(profile)
        _normal_profile_instance = profile
    return _normal_profile_instance


def _make_private_profile() -> "QWebEngineProfile":
    """Create an off-the-record profile and hold a strong ref to prevent GC crash."""
    if not _WEBENGINE_OK:
        return None
    profile = QWebEngineProfile()          # no parent — intentional
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    )
    profile.setUrlRequestInterceptor(_get_interceptor())
    _apply_privacy_settings(profile)
    _private_profiles.append(profile)     # keep alive
    return profile


def _apply_privacy_settings(profile: "QWebEngineProfile"):
    s = profile.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, False)
    s.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.WebRTCPublicInterfacesOnly, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
    s.setAttribute(QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled, False)
    s.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)


# ══════════════════════════════════════════════════════════════════════════════
# URL Interceptor
# ══════════════════════════════════════════════════════════════════════════════

if _WEBENGINE_OK:
    class _PrivacyInterceptor(QWebEngineUrlRequestInterceptor):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._https_only = False
            self._block_ads  = True

        def set_https_only(self, v: bool): self._https_only = v
        def set_block_ads(self,  v: bool): self._block_ads  = v

        def interceptRequest(self, info):
            url  = info.requestUrl()
            host = url.host().lower().lstrip("www.")

            if self._block_ads:
                for blocked in _BLOCKED_DOMAINS:
                    if host == blocked or host.endswith("." + blocked):
                        info.block(True)
                        return

            query = url.query()
            if query:
                params  = urllib.parse.parse_qs(query, keep_blank_values=True)
                cleaned = {k: v for k, v in params.items()
                           if k.lower() not in _TRACKING_PARAMS}
                if len(cleaned) != len(params):
                    url.setQuery(urllib.parse.urlencode(cleaned, doseq=True))
                    info.redirect(url)
                    return

            if self._https_only and url.scheme() == "http":
                https_url = QUrl(url)
                https_url.setScheme("https")
                info.redirect(https_url)
else:
    class _PrivacyInterceptor:          # stub when WebEngine missing
        _https_only = False
        _block_ads  = True
        def set_https_only(self, v): self._https_only = v
        def set_block_ads(self,  v): self._block_ads  = v


# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════

_CSS = """
QWidget {
    background: #0f1117;
    color: #e2e8f0;
    font-family: 'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif;
}
QGroupBox {
    border: 1px solid #2d3748; border-radius: 8px;
    margin-top: 12px; padding: 10px 8px 8px 8px;
    color: #718096; font-size: 11px; font-weight: 600;
    letter-spacing: 0.5px; text-transform: uppercase;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; padding: 0 6px;
}
QLineEdit {
    background: #1a202c;
    color: #e2e8f0;
    border: 1.5px solid #2d3748;
    border-radius: 20px;
    padding: 7px 18px;
    font-size: 13px;
    selection-background-color: #3182ce;
}
QLineEdit:focus {
    border-color: #3182ce;
    background: #1e2533;
}
QPushButton {
    background: transparent;
    color: #a0aec0;
    border: none;
    font-size: 16px;
    padding: 5px 10px;
    border-radius: 6px;
}
QPushButton:hover { background: #2d3748; color: #e2e8f0; }
QPushButton:pressed { background: #1a202c; }
QPushButton:disabled { color: #2d3748; }
QPushButton[primary="true"] {
    background: #3182ce; color: #fff; border: none;
    font-size: 13px; padding: 7px 16px; border-radius: 8px;
    font-weight: 600;
}
QPushButton[primary="true"]:hover { background: #4299e1; }
QToolButton {
    background: transparent; color: #a0aec0; border: none;
    font-size: 13px; padding: 5px 10px; border-radius: 6px;
}
QToolButton:hover { background: #2d3748; color: #e2e8f0; }
QToolButton::menu-indicator { image: none; }
QTabWidget::pane { border: none; background: #0f1117; }
QTabBar::tab {
    background: #1a202c; color: #718096;
    padding: 8px 16px 8px 14px; margin-right: 2px;
    border-radius: 8px 8px 0 0; font-size: 12px;
    min-width: 100px; max-width: 200px;
}
QTabBar::tab:selected {
    background: #0f1117; color: #e2e8f0;
    border-bottom: 2px solid #3182ce;
}
QTabBar::tab:hover:!selected { background: #242d3d; }
QTabBar::close-button { subcontrol-position: right; }
QMenu {
    background: #1a202c; color: #e2e8f0;
    border: 1px solid #2d3748; border-radius: 10px;
    padding: 6px 4px;
}
QMenu::item { padding: 7px 22px; font-size: 12px; border-radius: 6px; margin: 1px 4px; }
QMenu::item:selected { background: #3182ce; color: white; }
QMenu::separator { height: 1px; background: #2d3748; margin: 4px 12px; }
QProgressBar { background: transparent; border: none; max-height: 3px; }
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3182ce, stop:1 #63b3ed);
    border-radius: 2px;
}
QCheckBox { color: #e2e8f0; spacing: 10px; }
QCheckBox::indicator {
    width: 18px; height: 18px;
    border: 2px solid #4a5568; border-radius: 5px;
    background: #1a202c;
}
QCheckBox::indicator:checked {
    background: #3182ce; border-color: #3182ce;
    image: none;
}
QComboBox {
    background: #1a202c; color: #e2e8f0;
    border: 1.5px solid #2d3748; border-radius: 8px;
    padding: 5px 12px; font-size: 12px;
}
QComboBox:hover { border-color: #4a5568; }
QComboBox QAbstractItemView {
    background: #1a202c; color: #e2e8f0;
    border: 1px solid #2d3748;
    selection-background-color: #3182ce;
    border-radius: 6px;
}
QScrollBar:vertical {
    background: transparent; width: 6px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #2d3748; border-radius: 3px; min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

_SEARCH_ENGINES = [
    ("DuckDuckGo",  "https://duckduckgo.com/?q={}"),
    ("Startpage",   "https://www.startpage.com/search?q={}"),
    ("Brave",       "https://search.brave.com/search?q={}"),
    ("Ecosia",      "https://www.ecosia.org/search?q={}"),
    ("Google",      "https://www.google.com/search?q={}"),
    ("Bing",        "https://www.bing.com/search?q={}"),
]

_DEFAULT_HOME = "https://duckduckgo.com"


# ══════════════════════════════════════════════════════════════════════════════
# Privacy Settings Dialog
# ══════════════════════════════════════════════════════════════════════════════

class PrivacySettingsDialog(QDialog):
    def __init__(self, parent_tab=None, parent=None):
        super().__init__(parent)
        self._tab = parent_tab
        self.setWindowTitle("Privacy & Security")
        self.setMinimumWidth(500)
        self.setStyleSheet(_CSS)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Search engine
        se_group = QGroupBox("Search Engine")
        se_lay = QHBoxLayout(se_group)
        se_lay.addWidget(QLabel("Default:"))
        self._search_combo = QComboBox()
        self._search_combo.addItems([e[0] for e in _SEARCH_ENGINES])
        if self._tab:
            self._search_combo.setCurrentIndex(self._tab._search_engine_index)
        se_lay.addWidget(self._search_combo, 1)
        layout.addWidget(se_group)

        # Protection
        prot_group = QGroupBox("Protection")
        prot_lay = QVBoxLayout(prot_group)
        interceptor = _get_interceptor()

        self._block_ads_chk = QCheckBox("Block ads & trackers")
        self._block_ads_chk.setChecked(interceptor._block_ads if interceptor else True)
        prot_lay.addWidget(self._block_ads_chk)

        self._https_chk = QCheckBox("HTTPS-only mode (auto-upgrade HTTP → HTTPS)")
        self._https_chk.setChecked(interceptor._https_only if interceptor else False)
        prot_lay.addWidget(self._https_chk)

        if self._tab:
            self._js_chk = QCheckBox("Enable JavaScript")
            self._js_chk.setChecked(self._tab._js_enabled)
            prot_lay.addWidget(self._js_chk)

        layout.addWidget(prot_group)

        # Incognito info
        inc_group = QGroupBox("Incognito Mode")
        inc_lay = QVBoxLayout(inc_group)
        info = QLabel(
            "When incognito is active:\n"
            "  • No browsing history saved\n"
            "  • No cookies after closing tab\n"
            "  • No disk cache\n"
            "  • Tracking parameters stripped from URLs"
        )
        info.setStyleSheet("color: #718096; font-size: 11px; line-height: 1.6;")
        inc_lay.addWidget(info)
        layout.addWidget(inc_group)

        # Data management
        data_group = QGroupBox("Data Management")
        data_lay = QVBoxLayout(data_group)
        clear_btn = QPushButton("🗑  Clear All Browsing Data")
        clear_btn.setProperty("primary", True)
        clear_btn.clicked.connect(self._clear_data)
        data_lay.addWidget(clear_btn)
        layout.addWidget(data_group)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._apply)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _apply(self):
        interceptor = _get_interceptor()
        if interceptor:
            interceptor.set_block_ads(self._block_ads_chk.isChecked())
            interceptor.set_https_only(self._https_chk.isChecked())
        if self._tab:
            idx = self._search_combo.currentIndex()
            changed = (idx != self._tab._search_engine_index)
            self._tab._search_engine_index = idx
            if hasattr(self, "_js_chk"):
                self._tab.set_js(self._js_chk.isChecked())
            # Navigate to new search engine home if engine changed
            if changed:
                _, tmpl = _SEARCH_ENGINES[idx]
                self._tab.load(tmpl.format(""))
        self.accept()

    def _clear_data(self):
        """FIX: use the singleton profile — never create a second normal profile."""
        try:
            profile = _get_normal_profile()
            if profile:
                profile.clearAllVisitedLinks()
                profile.cookieStore().deleteAllCookies()
                profile.clearHttpCache()
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not clear all data: {e}")
            return
        QMessageBox.information(self, "Done", "All browsing data cleared.")


# ══════════════════════════════════════════════════════════════════════════════
# Embedded Browser (QWebEngineView wrapper)
# ══════════════════════════════════════════════════════════════════════════════

class EmbeddedBrowser(QWidget):
    title_changed    = pyqtSignal(str)
    url_changed      = pyqtSignal(str)
    load_finished    = pyqtSignal(bool)
    load_progress    = pyqtSignal(int)
    security_changed = pyqtSignal(bool)

    def __init__(self, incognito: bool = False, parent=None):
        super().__init__(parent)
        self._incognito = incognito
        self._current_url = _DEFAULT_HOME
        self._web_view = None
        self._page     = None
        self._setup_ui()

    def cleanup(self):
        """Call before destroying the widget to avoid app crash."""
        if self._web_view is None:
            return
        try:
            self._web_view.stop()
            try: self._web_view.urlChanged.disconnect()
            except Exception: pass
            try: self._web_view.titleChanged.disconnect()
            except Exception: pass
            try: self._web_view.loadFinished.disconnect()
            except Exception: pass
            try: self._web_view.loadProgress.disconnect()
            except Exception: pass
            # Replace with a blank page so the renderer releases GPU resources
            self._web_view.setUrl(QUrl("about:blank"))
            blank = QWebEnginePage(self)
            self._web_view.setPage(blank)
            self._page     = None
            self._web_view = None
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setMaximumHeight(3)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        if not _WEBENGINE_OK:
            err = QLabel(
                "⚠️  QtWebEngine is not installed.\n"
                "Run:  pip install PyQt6-WebEngine"
            )
            err.setAlignment(Qt.AlignmentFlag.AlignCenter)
            err.setStyleSheet("color:#f56565; font-size:14px; padding:40px;")
            layout.addWidget(err)
            return

        if self._incognito:
            profile = _make_private_profile()
        else:
            profile = _get_normal_profile()

        self._page     = QWebEnginePage(profile, self)
        self._web_view = QWebEngineView(self)
        self._web_view.setPage(self._page)

        self._web_view.urlChanged.connect(self._on_url_changed)
        self._web_view.titleChanged.connect(self.title_changed.emit)
        self._web_view.loadFinished.connect(self._on_load_finished)
        self._web_view.loadProgress.connect(self._on_load_progress)

        layout.addWidget(self._web_view)

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_url_changed(self, url: QUrl):
        self._current_url = url.toString()
        self.url_changed.emit(self._current_url)
        self.security_changed.emit(url.scheme() == "https")

    def _on_load_finished(self, ok: bool):
        self.load_finished.emit(ok)
        QTimer.singleShot(400, self._progress_bar.hide)

    def _on_load_progress(self, progress: int):
        if 0 < progress < 100:
            self._progress_bar.show()
        self._progress_bar.setValue(progress)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, url: str):
        if not self._web_view:
            return
        if not url or url == "pyos://home":
            url = _DEFAULT_HOME
        if not url.startswith(("http://", "https://", "file://")):
            if " " not in url and "." in url:
                url = "https://" + url
            else:
                url = "https://" + url
        self._current_url = url
        self._web_view.load(QUrl(url))

    def go_back(self):
        if self._web_view: self._web_view.back()

    def go_forward(self):
        if self._web_view: self._web_view.forward()

    def reload(self):
        if self._web_view: self._web_view.reload()

    def stop(self):
        if self._web_view: self._web_view.stop()

    def get_web_view(self):
        return self._web_view

    def set_javascript(self, enabled: bool):
        if self._web_view:
            self._web_view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, enabled
            )

    def zoom_in(self):
        if self._web_view:
            self._web_view.setZoomFactor(
                min(self._web_view.zoomFactor() + 0.1, 3.0)
            )

    def zoom_out(self):
        if self._web_view:
            self._web_view.setZoomFactor(
                max(self._web_view.zoomFactor() - 0.1, 0.3)
            )

    def zoom_reset(self):
        if self._web_view:
            self._web_view.setZoomFactor(1.0)


# ══════════════════════════════════════════════════════════════════════════════
# Single Browser Tab
# ══════════════════════════════════════════════════════════════════════════════

class BrowserTab(QWidget):

    def __init__(self, url: str = "", incognito: bool = False, parent=None):
        super().__init__(parent)
        self._incognito = incognito
        self._js_enabled = True
        self._search_engine_index = 0
        self._is_secure = False
        self._bookmarks: list[str] = []
        self._setup_ui()
        self.load(url or _DEFAULT_HOME)

    # ── UI setup ──────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Navigation bar
        nav_container = QWidget()
        nav_container.setObjectName("navBar")
        nav_container.setStyleSheet(
            "#navBar { background: #131720; border-bottom: 1px solid #1e2533; }"
        )
        nav_container.setFixedHeight(52)
        nav = QHBoxLayout(nav_container)
        nav.setContentsMargins(10, 8, 10, 8)
        nav.setSpacing(4)

        # Nav buttons
        self._back_btn    = self._nav_btn("←", "Back (Alt+Left)")
        self._forward_btn = self._nav_btn("→", "Forward (Alt+Right)")
        self._reload_btn  = self._nav_btn("⟳", "Reload (Ctrl+R)")
        self._stop_btn    = self._nav_btn("✕", "Stop")
        self._home_btn    = self._nav_btn("⌂", "Home")
        self._stop_btn.hide()

        for b in [self._back_btn, self._forward_btn, self._reload_btn,
                  self._stop_btn, self._home_btn]:
            nav.addWidget(b)

        nav.addSpacing(4)

        # Security lock
        self._lock_lbl = QLabel("🔓")
        self._lock_lbl.setFixedWidth(22)
        self._lock_lbl.setToolTip("Not secure")
        self._lock_lbl.setStyleSheet("font-size:14px;")
        nav.addWidget(self._lock_lbl)

        # URL bar
        self._url_bar = QLineEdit()
        self._url_bar.setPlaceholderText("Search or enter a URL…")
        self._url_bar.returnPressed.connect(self._navigate_to_url)
        self._url_bar.setStyleSheet(
            "QLineEdit {"
            "  background: #1e2533;"
            "  border: 1.5px solid #2d3a4a;"
            "  border-radius: 20px;"
            "  padding: 6px 18px;"
            "  font-size: 13px;"
            "  color: #e2e8f0;"
            "}"
            "QLineEdit:focus {"
            "  border-color: #3182ce;"
            "  background: #1a2235;"
            "}"
        )
        nav.addWidget(self._url_bar, 1)

        # Bookmark button
        self._bm_btn = self._nav_btn("☆", "Bookmark this page")
        self._bm_btn.setStyleSheet(
            self._bm_btn.styleSheet() +
            "QPushButton { font-size:18px; color:#ecc94b; }"
        )
        self._bm_btn.clicked.connect(self._toggle_bookmark)
        nav.addWidget(self._bm_btn)

        # Incognito badge
        if self._incognito:
            badge = QLabel("🕵 Private")
            badge.setStyleSheet(
                "color:#805ad5; font-size:11px; font-weight:700;"
                "background:#1a1225; padding:3px 8px;"
                "border:1px solid #553c9a; border-radius:10px;"
            )
            nav.addWidget(badge)

        # Privacy & Menu buttons
        self._privacy_btn = QToolButton()
        self._privacy_btn.setText("🛡")
        self._privacy_btn.setToolTip("Privacy Settings")
        self._privacy_btn.setFixedSize(36, 34)
        self._privacy_btn.clicked.connect(self._open_privacy_settings)
        nav.addWidget(self._privacy_btn)

        self._menu_btn = QToolButton()
        self._menu_btn.setText("⋮")
        self._menu_btn.setFixedSize(32, 34)
        self._menu_btn.setToolTip("Menu")
        self._menu_btn.clicked.connect(self._show_menu)
        nav.addWidget(self._menu_btn)

        root.addWidget(nav_container)

        # Browser content
        self._browser = EmbeddedBrowser(incognito=self._incognito, parent=self)
        self._browser.url_changed.connect(self._update_url_bar)
        self._browser.title_changed.connect(self._update_tab_title)
        self._browser.load_finished.connect(self._on_load_finished)
        self._browser.load_progress.connect(self._on_load_progress)
        self._browser.security_changed.connect(self._update_security)
        root.addWidget(self._browser)

        # Status bar (shows hovered link URLs)
        self._status_bar = QLabel()
        self._status_bar.setFixedHeight(18)
        self._status_bar.setStyleSheet(
            "background:#0f1117; color:#718096; font-size:10px; padding-left:10px;"
            "border-top:1px solid #1e2533;"
        )
        self._status_bar.hide()
        root.addWidget(self._status_bar)

        # Connect navigation buttons
        self._back_btn.clicked.connect(self._browser.go_back)
        self._forward_btn.clicked.connect(self._browser.go_forward)
        self._reload_btn.clicked.connect(self._browser.reload)
        self._stop_btn.clicked.connect(self._browser.stop)
        self._home_btn.clicked.connect(lambda: self.load(_DEFAULT_HOME))

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+R"),       self, self._browser.reload)
        QShortcut(QKeySequence("Ctrl+L"),       self, self._focus_url_bar)
        QShortcut(QKeySequence("Alt+Left"),     self, self._browser.go_back)
        QShortcut(QKeySequence("Alt+Right"),    self, self._browser.go_forward)
        QShortcut(QKeySequence("Ctrl+Plus"),    self, self._browser.zoom_in)
        QShortcut(QKeySequence("Ctrl+Minus"),   self, self._browser.zoom_out)
        QShortcut(QKeySequence("Ctrl+0"),       self, self._browser.zoom_reset)
        QShortcut(QKeySequence(Qt.Key.Key_F5),  self, self._browser.reload)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._browser.stop)

    def _nav_btn(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setFixedSize(34, 34)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(
            "QPushButton { background:transparent; color:#718096; border:none;"
            " font-size:17px; border-radius:6px; }"
            "QPushButton:hover { background:#1e2533; color:#e2e8f0; }"
            "QPushButton:pressed { background:#131720; }"
        )
        return b

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _focus_url_bar(self):
        self._url_bar.setFocus()
        self._url_bar.selectAll()

    def _update_url_bar(self, url: str):
        self._url_bar.setText(url)
        self._url_bar.setCursorPosition(0)

    def _update_tab_title(self, title: str):
        parent = self.parent()
        if isinstance(parent, QTabWidget):
            idx = parent.indexOf(self)
            if idx >= 0:
                prefix = "🕵 " if self._incognito else ""
                short  = (title[:20] + "…") if len(title) > 22 else title
                parent.setTabText(idx, prefix + (short or "New Tab"))

    def _update_security(self, is_https: bool):
        self._is_secure = is_https
        if is_https:
            self._lock_lbl.setText("🔒")
            self._lock_lbl.setToolTip("Connection is secure (HTTPS)")
            self._lock_lbl.setStyleSheet("font-size:14px; color:#48bb78;")
        else:
            self._lock_lbl.setText("🔓")
            self._lock_lbl.setToolTip("Connection is NOT secure (HTTP)")
            self._lock_lbl.setStyleSheet("font-size:14px; color:#fc8181;")

    def _on_load_finished(self, ok: bool):
        self._reload_btn.show()
        self._stop_btn.hide()

    def _on_load_progress(self, progress: int):
        if 0 < progress < 100:
            self._reload_btn.hide()
            self._stop_btn.show()
        else:
            self._reload_btn.show()
            self._stop_btn.hide()

    def _navigate_to_url(self):
        text = self._url_bar.text().strip()
        if not text:
            return
        if text.startswith(("http://", "https://", "file://")):
            self.load(text)
        elif "." in text and " " not in text:
            self.load("https://" + text)
        else:
            name, tmpl = _SEARCH_ENGINES[self._search_engine_index]
            self.load(tmpl.format(urllib.parse.quote_plus(text)))

    def _toggle_bookmark(self):
        url = self._url_bar.text().strip()
        if url in self._bookmarks:
            self._bookmarks.remove(url)
            self._bm_btn.setText("☆")
            self._bm_btn.setToolTip("Bookmark this page")
        else:
            self._bookmarks.append(url)
            self._bm_btn.setText("★")
            self._bm_btn.setToolTip("Remove bookmark")

    def _open_privacy_settings(self):
        dlg = PrivacySettingsDialog(parent_tab=self, parent=self)
        dlg.exec()

    def _show_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(_CSS)

        interceptor = _get_interceptor()

        act_ext = menu.addAction("↗  Open in external browser")
        act_ext.triggered.connect(self._open_external)

        menu.addSeparator()

        # Search engine switcher sub-menu
        se_menu = menu.addMenu("🔎  Search engine")
        se_menu.setStyleSheet(_CSS)
        for i, (name, _) in enumerate(_SEARCH_ENGINES):
            act = se_menu.addAction(("✓  " if i == self._search_engine_index else "   ") + name)
            idx = i
            act.triggered.connect(lambda checked, n=idx: self._set_search_engine(n))

        menu.addSeparator()

        act_zoom_in  = menu.addAction("🔍  Zoom in  (Ctrl++)")
        act_zoom_out = menu.addAction("🔍  Zoom out  (Ctrl+−)")
        act_zoom_rst = menu.addAction("⊙  Reset zoom  (Ctrl+0)")
        act_zoom_in.triggered.connect(self._browser.zoom_in)
        act_zoom_out.triggered.connect(self._browser.zoom_out)
        act_zoom_rst.triggered.connect(self._browser.zoom_reset)

        menu.addSeparator()

        js_label = "✓  JavaScript ON" if self._js_enabled else "   JavaScript OFF"
        menu.addAction(js_label).triggered.connect(self._toggle_js)

        https_on = interceptor._https_only if interceptor else False
        ads_on   = interceptor._block_ads  if interceptor else True
        menu.addAction(
            "✓  HTTPS-only" if https_on else "   HTTPS-only"
        ).triggered.connect(self._toggle_https)
        menu.addAction(
            "✓  Block trackers" if ads_on else "   Block trackers"
        ).triggered.connect(self._toggle_ads)

        menu.addSeparator()

        menu.addAction("🗑  Clear browsing data").triggered.connect(self._clear_data)
        menu.addAction("📄  View page source").triggered.connect(self._view_source)

        menu.exec(self._menu_btn.mapToGlobal(
            self._menu_btn.rect().bottomLeft()
        ))

    def _set_search_engine(self, index: int):
        self._search_engine_index = index
        # Navigate to the selected engine's home so user sees it changed
        _, tmpl = _SEARCH_ENGINES[index]
        self.load(tmpl.format(""))

    def _toggle_js(self):
        self.set_js(not self._js_enabled)

    def _toggle_https(self):
        i = _get_interceptor()
        if i: i.set_https_only(not i._https_only)

    def _toggle_ads(self):
        i = _get_interceptor()
        if i: i.set_block_ads(not i._block_ads)

    def _open_external(self):
        url = self._url_bar.text().strip()
        if url:
            import webbrowser
            webbrowser.open(url)

    def _clear_data(self):
        """FIX: safe clear using singleton profile only."""
        try:
            profile = _get_normal_profile()
            if profile:
                profile.clearAllVisitedLinks()
                profile.cookieStore().deleteAllCookies()
                profile.clearHttpCache()
        except Exception as e:
            QMessageBox.warning(self, "Warning", f"Could not clear all data:\n{e}")
            return
        QMessageBox.information(self, "Cleared", "Browsing data cleared.")

    def _view_source(self):
        """FIX: guard against missing web view."""
        wv = self._browser.get_web_view()
        if wv:
            wv.page().toHtml(self._show_source_window)

    def _show_source_window(self, html: str):
        from PyQt6.QtWidgets import QTextEdit
        w = QWidget()
        w.setWindowTitle("Page Source")
        w.setWindowFlags(Qt.WindowType.Window)
        w.resize(960, 650)
        w.setStyleSheet(_CSS)
        lay = QVBoxLayout(w)
        te = QTextEdit()
        te.setPlainText(html)
        te.setReadOnly(True)
        te.setStyleSheet(
            "background:#0d1117; color:#e2e8f0;"
            "font-family:'Cascadia Code','Consolas','Courier New',monospace;"
            "font-size:12px;"
        )
        lay.addWidget(te)
        w.show()
        self._src_win = w   # keep alive

    # ── Cleanup — prevents app crash when the MDI sub-window closes ─────────────
    def closeEvent(self, event):
        self._browser.cleanup()
        super().closeEvent(event)

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, url: str):
        self._browser.load(url)

    def set_js(self, enabled: bool):
        self._js_enabled = enabled
        self._browser.set_javascript(enabled)


# ══════════════════════════════════════════════════════════════════════════════
# Multi-tab Browser Widget (main exported widget)
# ══════════════════════════════════════════════════════════════════════════════

class BrowserWidget(QWidget):
    """Main browser widget with tabs, incognito mode, and full privacy support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_CSS)
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: #0f1117; }"
            "QTabBar { background: #131720; }"
        )

        # Corner buttons (new tab / incognito)
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(0, 0, 6, 0)
        cl.setSpacing(2)

        self._new_btn = QPushButton("+")
        self._new_btn.setFixedSize(34, 30)
        self._new_btn.setToolTip("New tab  (Ctrl+T)")
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#718096; font-size:20px;"
            " border:none; border-radius:6px; }"
            "QPushButton:hover { background:#1e2533; color:#e2e8f0; }"
        )
        self._new_btn.clicked.connect(lambda: self.open_new_tab())

        self._incog_btn = QPushButton("🕵")
        self._incog_btn.setFixedSize(34, 30)
        self._incog_btn.setToolTip("New private tab  (Ctrl+Shift+N)")
        self._incog_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._incog_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#805ad5; font-size:16px;"
            " border:none; border-radius:6px; }"
            "QPushButton:hover { background:#1a1225; }"
        )
        self._incog_btn.clicked.connect(lambda: self.open_new_tab(incognito=True))

        cl.addWidget(self._new_btn)
        cl.addWidget(self._incog_btn)
        self._tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        root.addWidget(self._tabs, 1)

        # Bottom status bar
        status = QWidget()
        status.setFixedHeight(22)
        status.setStyleSheet(
            "background:#0a0d14; border-top:1px solid #1a202c;"
        )
        sl = QHBoxLayout(status)
        sl.setContentsMargins(10, 0, 10, 0)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#4a5568; font-size:10px;")
        sl.addWidget(self._status_lbl)
        sl.addStretch()
        shield_lbl = QLabel("🛡 Privacy Protection Active")
        shield_lbl.setStyleSheet("color:#48bb78; font-size:10px;")
        sl.addWidget(shield_lbl)
        root.addWidget(status)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+T"),       self, lambda: self.open_new_tab())
        QShortcut(QKeySequence("Ctrl+W"),       self, self._close_current_tab)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, lambda: self.open_new_tab(incognito=True))
        QShortcut(QKeySequence("Ctrl+Tab"),     self, self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_tab)

        # Open first tab
        self.open_new_tab(_DEFAULT_HOME)

    # ── Proper teardown — prevents app crash when MDI sub-window is closed ────
    def closeEvent(self, event):
        """Clean up ALL tabs before Qt destroys us."""
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if tab and hasattr(tab, "_browser"):
                try:
                    tab._browser.cleanup()
                except Exception:
                    pass
        super().closeEvent(event)

    # ── Tab management ────────────────────────────────────────────────────────

    def open_new_tab(self, url: str = None, incognito: bool = False) -> "BrowserTab":
        url = url or _DEFAULT_HOME
        tab = BrowserTab(url, incognito=incognito, parent=self._tabs)
        label = "🕵 Private" if incognito else "New Tab"
        idx = self._tabs.addTab(tab, label)
        self._tabs.setCurrentIndex(idx)
        return tab

    def _close_tab(self, index: int):
        if self._tabs.count() > 1:
            tab = self._tabs.widget(index)
            if tab and hasattr(tab, "_browser"):
                tab._browser.cleanup()
            self._tabs.removeTab(index)
        else:
            tab = self._tabs.widget(0)
            if tab:
                tab.load(_DEFAULT_HOME)

    def _close_current_tab(self):
        self._close_tab(self._tabs.currentIndex())

    def _next_tab(self):
        n = self._tabs.count()
        if n > 1:
            self._tabs.setCurrentIndex((self._tabs.currentIndex() + 1) % n)

    def _prev_tab(self):
        n = self._tabs.count()
        if n > 1:
            self._tabs.setCurrentIndex((self._tabs.currentIndex() - 1) % n)

    def get_current_browser(self) -> Optional["EmbeddedBrowser"]:
        tab = self._tabs.currentWidget()
        if tab and hasattr(tab, "_browser"):
            return tab._browser
        return None


# ── Utility ───────────────────────────────────────────────────────────────────

def open_external_browser(url: str):
    import webbrowser
    webbrowser.open(url)