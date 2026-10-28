"""
System Monitor Module
Polls real CPU, memory, and disk stats via psutil.
Uses QThread to avoid blocking the UI.
"""

import time
import psutil
from PyQt6.QtCore import QThread, pyqtSignal, QObject


class MonitorThread(QThread):
    statsReady = pyqtSignal(dict)

    def __init__(self, interval_ms: int = 2000, parent=None):
        super().__init__(parent)
        self._interval = interval_ms / 1000
        self._running = True

    def run(self):
        while self._running:
            stats = self._collect()
            self.statsReady.emit(stats)
            time.sleep(self._interval)

    def stop(self):
        self._running = False

    def _collect(self) -> dict:
        cpu_pct = psutil.cpu_percent(interval=None)
        cpu_per_core = psutil.cpu_percent(percpu=True, interval=None)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()

        cores = [{"core": i, "pct": p} for i, p in enumerate(cpu_per_core)]

        return {
            "cpu": {
                "total_pct": cpu_pct,
                "cores": cores,
                "count_logical": psutil.cpu_count(logical=True),
                "count_physical": psutil.cpu_count(logical=False),
                "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
            },
            "memory": {
                "total_gb": round(mem.total / 1e9, 2),
                "used_gb": round(mem.used / 1e9, 2),
                "free_gb": round(mem.available / 1e9, 2),
                "pct": mem.percent,
                "swap_total_gb": round(swap.total / 1e9, 2),
                "swap_used_gb": round(swap.used / 1e9, 2),
                "swap_pct": swap.percent,
            },
            "disk": {
                "total_gb": round(disk.total / 1e9, 2),
                "used_gb": round(disk.used / 1e9, 2),
                "free_gb": round(disk.free / 1e9, 2),
                "pct": disk.percent,
            },
            "network": {
                "bytes_sent_mb": round(net.bytes_sent / 1e6, 2),
                "bytes_recv_mb": round(net.bytes_recv / 1e6, 2),
                "packets_sent": net.packets_sent,
                "packets_recv": net.packets_recv,
            },
            "timestamp": time.time(),
        }


class SystemMonitor(QObject):
    statsUpdated = pyqtSignal(dict)

    def __init__(self, interval_ms: int = 2000, parent=None):
        super().__init__(parent)
        self._thread = MonitorThread(interval_ms, self)
        self._thread.statsReady.connect(self.statsUpdated)

    def start(self):
        self._thread.start()

    def stop(self):
        self._thread.stop()
        self._thread.wait(3000)
