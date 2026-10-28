"""
Settings Manager
Handles loading, saving, and distributing persistent settings
stored at ~/.pyos/settings.json.

Usage:
    from settings_manager import SettingsManager
    sm = SettingsManager()
    sm.set("theme", "light")
    val = sm.get("theme")
    sm.subscribe("theme", callback)   # called whenever key changes
"""

import json
import os
import threading
from typing import Any, Callable, Dict, List

CONFIG_DIR = os.path.expanduser("~/.pyos")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS: Dict[str, Any] = {
    "theme":                  "dark",
    "accent_color":           "#0078d4",
    "background_style":       "Aurora",
    "background_image":       "",
    "font_size":              10,
    "animations_enabled":     True,
    "dock_position":          "bottom",
    "auto_optimize":          False,
    "terminal_shell":         "",
    "monitor_interval_ms":    2000,
    "network_scan_interval_s": 30,
}


class SettingsManager:
    """Thread-safe persistent settings store."""

    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = dict(DEFAULTS)
        self._listeners: Dict[str, List[Callable]] = {}
        self._load()

    def _load(self):
        try:
            if os.path.isfile(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    stored = json.load(f)
                with self._lock:
                    self._data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except Exception:
            pass

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with self._lock:
                snapshot = dict(self._data)
            with open(CONFIG_FILE, "w") as f:
                json.dump(snapshot, f, indent=2)
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key: str, value: Any):
        with self._lock:
            if self._data.get(key) == value:
                return
            self._data[key] = value
        self.save()
        for cb in self._listeners.get(key, []):
            try:
                cb(value)
            except Exception:
                pass
        for cb in self._listeners.get("*", []):
            try:
                cb(key, value)
            except Exception:
                pass

    def all(self) -> dict:
        with self._lock:
            return dict(self._data)

    def subscribe(self, key: str, callback: Callable):
        """Subscribe to changes on a specific key, or '*' for all keys."""
        self._listeners.setdefault(key, []).append(callback)

    def unsubscribe(self, key: str, callback: Callable):
        lst = self._listeners.get(key, [])
        if callback in lst:
            lst.remove(callback)


_instance: SettingsManager | None = None


def get_settings() -> SettingsManager:
    global _instance
    if _instance is None:
        _instance = SettingsManager()
    return _instance
