"""
I/O Device Manager Module
Tracks real and simulated I/O devices, keyboard/mouse events.
"""

import threading
import time
import platform
import psutil
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication


class DeviceState:
    AVAILABLE = "Available"
    BUSY = "Busy"
    OFFLINE = "Offline"


@dataclass
class IODevice:
    device_id: str
    name: str
    device_type: str
    state: str = DeviceState.AVAILABLE
    value: str = ""
    queue_depth: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.device_id,
            "name": self.name,
            "type": self.device_type,
            "state": self.state,
            "value": self.value,
            "queue": self.queue_depth,
        }


class IOManager(QObject):
    """
    Polls real hardware info and simulates device I/O queues.
    Emits devicesUpdated whenever readings change.
    """

    devicesUpdated = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._devices: Dict[str, IODevice] = {}
        self._mouse_x = 0
        self._mouse_y = 0
        self._key_last = ""
        self._init_devices()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(2000)

    def _init_devices(self):
        devs = [
            IODevice("kbd",     "Keyboard",         "keyboard"),
            IODevice("mouse",   "Mouse / Pointer",  "mouse"),
            IODevice("screen",  "Display",          "screen"),
            IODevice("cpu",     "CPU",              "cpu"),
            IODevice("battery", "Battery",          "battery"),
            IODevice("disk",    "Primary Disk",     "disk"),
            IODevice("net",     "Network Interface","network"),
        ]
        for d in devs:
            self._devices[d.device_id] = d
        self._poll()

    def _poll(self):
        self._update_mouse()
        self._update_screen()
        self._update_cpu()
        self._update_battery()
        self._update_disk()
        self._update_network()
        self.devicesUpdated.emit(self.get_all())

    def _update_mouse(self):
        d = self._devices["mouse"]
        d.value = f"({self._mouse_x}, {self._mouse_y})"
        d.state = DeviceState.AVAILABLE

    def _update_screen(self):
        d = self._devices["screen"]
        try:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                dpi = screen.physicalDotsPerInch()
                d.value = f"{geo.width()}×{geo.height()} @ {dpi:.0f} DPI"
                d.state = DeviceState.AVAILABLE
        except Exception:
            d.value = "Unknown"

    def _update_cpu(self):
        d = self._devices["cpu"]
        try:
            cores = psutil.cpu_count(logical=True)
            usage = psutil.cpu_percent(interval=None)
            freq = psutil.cpu_freq()
            freq_str = f" {freq.current:.0f} MHz" if freq else ""
            d.value = f"{cores} cores{freq_str} | {usage:.1f}% used"
            d.state = DeviceState.BUSY if usage > 80 else DeviceState.AVAILABLE
        except Exception:
            d.value = "N/A"

    def _update_battery(self):
        d = self._devices["battery"]
        try:
            bat = psutil.sensors_battery()
            if bat is None:
                d.value = "AC Power / No battery"
                d.state = DeviceState.OFFLINE
            else:
                status = "Charging" if bat.power_plugged else "Discharging"
                d.value = f"{bat.percent:.0f}% ({status})"
                d.state = DeviceState.AVAILABLE
        except Exception:
            d.value = "N/A"
            d.state = DeviceState.OFFLINE

    def _update_disk(self):
        d = self._devices["disk"]
        try:
            usage = psutil.disk_usage('/')
            total_gb = usage.total / 1e9
            used_gb = usage.used / 1e9
            d.value = f"{used_gb:.1f} GB / {total_gb:.1f} GB ({usage.percent:.0f}%)"
            d.state = DeviceState.AVAILABLE
        except Exception:
            d.value = "N/A"

    def _update_network(self):
        d = self._devices["net"]
        try:
            counters = psutil.net_io_counters()
            sent_mb = counters.bytes_sent / 1e6
            recv_mb = counters.bytes_recv / 1e6
            d.value = f"↑ {sent_mb:.1f} MB | ↓ {recv_mb:.1f} MB"
            d.state = DeviceState.AVAILABLE
        except Exception:
            d.value = "N/A"

    def on_mouse_move(self, x: int, y: int):
        self._mouse_x = x
        self._mouse_y = y
        d = self._devices["mouse"]
        d.value = f"({x}, {y})"
        d.queue_depth = min(d.queue_depth + 1, 8)

    def on_key_press(self, key: str):
        d = self._devices["kbd"]
        d.state = DeviceState.BUSY
        d.value = f"Last key: {key!r}"
        d.queue_depth = min(d.queue_depth + 1, 16)
        self._key_last = key

    def on_key_release(self):
        d = self._devices["kbd"]
        d.state = DeviceState.AVAILABLE
        if d.queue_depth > 0:
            d.queue_depth -= 1

    def get_all(self) -> List[dict]:
        return [d.to_dict() for d in self._devices.values()]
