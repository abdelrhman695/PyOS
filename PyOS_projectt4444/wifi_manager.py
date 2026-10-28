"""
Wi-Fi Manager Module
Real Wi-Fi integration using OS-level tools:
  Linux  → nmcli
  macOS  → airport + networksetup
  Windows→ netsh wlan
"""

import subprocess
import platform
import re
import time
from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QLineEdit, QDialog, QDialogButtonBox, QMessageBox, QFrame
)


@dataclass
class WifiNetwork:
    ssid: str
    bssid: str = ""
    signal: int = 0
    security: str = ""
    connected: bool = False
    frequency: str = ""

    def signal_icon(self) -> str:
        if self.signal >= 75: return "▂▄▆█"
        if self.signal >= 50: return "▂▄▆░"
        if self.signal >= 25: return "▂▄░░"
        return "▂░░░"

    def signal_color(self) -> str:
        if self.signal >= 65: return "#3fb950"
        if self.signal >= 35: return "#f0ad4e"
        return "#f85149"


def _run(cmd: list, timeout: float = 15) -> tuple[str, int]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout + r.stderr, r.returncode
    except FileNotFoundError:
        return f"[tool not found: {cmd[0]}]", -1
    except subprocess.TimeoutExpired:
        return "[timeout]", -1
    except Exception as e:
        return str(e), -1


def _current_ssid_linux() -> str:
    out, _ = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "device", "wifi"], 5)
    for line in out.splitlines():
        if line.startswith("yes:"):
            return line[4:].strip()
    return ""


def _scan_linux() -> tuple[List[WifiNetwork], str]:
    out, rc = _run(["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY,FREQ",
                    "device", "wifi", "list", "--rescan", "yes"])
    if rc < 0:
        return [], out
    current = _current_ssid_linux()
    networks: List[WifiNetwork] = []
    seen = set()
    for line in out.strip().splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        ssid = parts[0].strip() or "(hidden)"
        if ssid in seen:
            continue
        seen.add(ssid)
        try:
            signal = int(parts[2]) if parts[2].strip().lstrip('-').isdigit() else 0
        except (ValueError, IndexError):
            signal = 0
        bssid = parts[1] if len(parts) > 1 else ""
        security = parts[3].strip() if len(parts) > 3 else ""
        freq = parts[4].strip() if len(parts) > 4 else ""
        networks.append(WifiNetwork(
            ssid=ssid, bssid=bssid, signal=signal,
            security=security, connected=(ssid == current), frequency=freq
        ))
    return networks, ""


def _connect_linux(ssid: str, password: str) -> tuple[bool, str]:
    if password:
        cmd = ["nmcli", "device", "wifi", "connect", ssid, "password", password]
    else:
        cmd = ["nmcli", "device", "wifi", "connect", ssid]
    out, rc = _run(cmd, 30)
    return rc == 0, out.strip()


def _disconnect_linux() -> tuple[bool, str]:
    out, _ = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"])
    device = "wifi"
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[1] == "wifi" and parts[2] == "connected":
            device = parts[0]
            break
    out2, rc = _run(["nmcli", "device", "disconnect", device], 10)
    return rc == 0, out2.strip()


def _scan_windows() -> tuple[List[WifiNetwork], str]:
    out, rc = _run(["netsh", "wlan", "show", "networks", "mode=bssid"])
    if rc < 0:
        return [], out
    iface_out, _ = _run(["netsh", "wlan", "show", "interfaces"])
    current_m = re.search(r"SSID\s*:\s*(.+)", iface_out)
    current = current_m.group(1).strip() if current_m else ""

    networks: List[WifiNetwork] = []
    blocks = re.split(r"\n(?=SSID \d)", out)
    for block in blocks:
        ssid_m = re.search(r"^SSID \d+\s*:\s*(.+)", block, re.M)
        sig_m = re.search(r"Signal\s*:\s*(\d+)%", block)
        auth_m = re.search(r"Authentication\s*:\s*(.+)", block)
        bssid_m = re.search(r"BSSID \d+\s*:\s*(.+)", block)
        if not ssid_m:
            continue
        ssid = ssid_m.group(1).strip()
        signal = int(sig_m.group(1)) if sig_m else 0
        security = auth_m.group(1).strip() if auth_m else ""
        bssid = bssid_m.group(1).strip() if bssid_m else ""
        networks.append(WifiNetwork(
            ssid=ssid, bssid=bssid, signal=signal,
            security=security, connected=(ssid == current)
        ))
    return networks, ""


def _scan_macos() -> tuple[List[WifiNetwork], str]:
    airport = (
        "/System/Library/PrivateFrameworks/Apple80211.framework"
        "/Versions/Current/Resources/airport"
    )
    out, rc = _run([airport, "-s"])
    if rc < 0:
        return [], out
    iface_out, _ = _run([airport, "-I"])
    current = ""
    for line in iface_out.splitlines():
        if "SSID:" in line and "BSSID" not in line:
            current = line.split(":")[-1].strip()
    networks: List[WifiNetwork] = []
    for line in out.strip().splitlines()[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        ssid = parts[0]
        try:
            rssi = int(parts[2])
            signal = max(0, min(100, 2 * (rssi + 100)))
        except (ValueError, IndexError):
            signal = 0
        security = " ".join(parts[6:]) if len(parts) > 6 else ""
        networks.append(WifiNetwork(ssid=ssid, signal=signal, security=security,
                                    connected=(ssid == current)))
    return networks, ""


def scan_wifi() -> tuple[List[WifiNetwork], str]:
    sys_name = platform.system().lower()
    if sys_name == "linux":
        return _scan_linux()
    elif sys_name == "darwin":
        return _scan_macos()
    elif sys_name == "windows":
        return _scan_windows()
    return [], "Unsupported platform"


def connect_wifi(ssid: str, password: str = "") -> tuple[bool, str]:
    sys_name = platform.system().lower()
    if sys_name == "linux":
        return _connect_linux(ssid, password)
    return False, "Connect only supported on Linux (nmcli) in this version."


def disconnect_wifi() -> tuple[bool, str]:
    sys_name = platform.system().lower()
    if sys_name == "linux":
        return _disconnect_linux()
    return False, "Disconnect only supported on Linux."


class WifiScanThread(QThread):
    scanComplete = pyqtSignal(list, str)

    def run(self):
        networks, err = scan_wifi()
        self.scanComplete.emit(networks, err)


class PasswordDialog(QDialog):
    def __init__(self, ssid: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Connect to {ssid}")
        self.setFixedSize(380, 160)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(QLabel(f"Password for <b>{ssid}</b>:"))
        self._pw = QLineEdit()
        self._pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw.setPlaceholderText("Wi-Fi password")
        self._pw.returnPressed.connect(self.accept)
        layout.addWidget(self._pw)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def password(self) -> str:
        return self._pw.text()


class WifiManagerWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._networks: List[WifiNetwork] = []
        self._scan_thread: Optional[WifiScanThread] = None
        self._build_ui()
        self._start_scan()

        self._auto = QTimer(self)
        self._auto.timeout.connect(self._start_scan)
        self._auto.start(30_000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        status_grp = QGroupBox("Connection Status")
        sl = QHBoxLayout(status_grp)
        self._status_icon = QLabel("📡")
        self._status_icon.setStyleSheet("font-size:18px; background:transparent;")
        sl.addWidget(self._status_icon)
        self._status_lbl = QLabel("Scanning…")
        self._status_lbl.setStyleSheet("font-size:13px; font-weight:600;")
        sl.addWidget(self._status_lbl, 1)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._disconnect)
        self._disconnect_btn.setEnabled(False)
        sl.addWidget(self._disconnect_btn)
        layout.addWidget(status_grp)

        toolbar = QHBoxLayout()
        self._scan_btn = QPushButton("🔄  Scan Networks")
        self._scan_btn.setProperty("primary", True)
        self._scan_btn.clicked.connect(self._start_scan)
        toolbar.addWidget(self._scan_btn)
        self._scan_lbl = QLabel("")
        self._scan_lbl.setStyleSheet("font-size:11px; color: #8b949e;")
        toolbar.addWidget(self._scan_lbl)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Network Name (SSID)", "Signal", "Security", ""])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.doubleClicked.connect(lambda: self._connect_selected())
        layout.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._connect_btn = QPushButton("Connect to Selected")
        self._connect_btn.setProperty("primary", True)
        self._connect_btn.clicked.connect(self._connect_selected)
        btn_row.addWidget(self._connect_btn)
        layout.addLayout(btn_row)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color: #f85149; font-size: 11px;")
        self._error_lbl.setWordWrap(True)
        layout.addWidget(self._error_lbl)

        note = QLabel("Double-click a network to connect  ·  Requires nmcli on Linux, netsh on Windows")
        note.setStyleSheet("color: #8b949e; font-size: 10px;")
        layout.addWidget(note)

    def _start_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self._scan_btn.setEnabled(False)
        self._scan_lbl.setText("Scanning…")
        self._error_lbl.clear()
        self._scan_thread = WifiScanThread(self)
        self._scan_thread.scanComplete.connect(self._on_scan_complete)
        self._scan_thread.start()

    def _on_scan_complete(self, networks: list, error: str):
        self._scan_btn.setEnabled(True)
        self._networks = networks
        if error and not networks:
            self._error_lbl.setText(f"⚠  {error}")
            self._scan_lbl.setText("Error")
            self._status_lbl.setText("Could not scan Wi-Fi")
            return
        self._scan_lbl.setText(f"Found {len(networks)} network(s)")
        self._populate()
        connected = next((n for n in networks if n.connected), None)
        if connected:
            self._status_icon.setText("✅")
            self._status_lbl.setText(f"Connected to: {connected.ssid}")
            self._status_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#3fb950;")
            self._disconnect_btn.setEnabled(True)
        else:
            self._status_icon.setText("📡")
            self._status_lbl.setText("Not connected")
            self._status_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#f85149;")
            self._disconnect_btn.setEnabled(False)

    def _populate(self):
        self._table.setRowCount(0)
        sorted_nets = sorted(self._networks, key=lambda n: -n.signal)
        for net in sorted_nets:
            idx = self._table.rowCount()
            self._table.insertRow(idx)
            self._table.setRowHeight(idx, 36)

            ssid_item = QTableWidgetItem(
                ("  ✓  " if net.connected else "     ") + net.ssid
            )
            if net.connected:
                ssid_item.setForeground(QColor("#3fb950"))
            self._table.setItem(idx, 0, ssid_item)

            sig_item = QTableWidgetItem(f"{net.signal_icon()}  {net.signal}%")
            sig_item.setForeground(QColor(net.signal_color()))
            sig_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(idx, 1, sig_item)

            sec = net.security or "Open"
            sec_item = QTableWidgetItem(f"🔒 {sec}" if net.security else "🔓 Open")
            sec_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(idx, 2, sec_item)

            btn = QPushButton("Connect" if not net.connected else "Connected")
            btn.setEnabled(not net.connected)
            btn.setStyleSheet(
                "QPushButton { background: #1f6feb; color: white; border: none;"
                "border-radius: 5px; padding: 4px 10px; font-size: 11px; }"
                "QPushButton:hover { background: #388bfd; }"
                "QPushButton:disabled { background: #2ea043; color: white; }"
            )
            net_ssid = net.ssid
            net_sec = net.security
            btn.clicked.connect(lambda _, s=net_ssid, sec=net_sec: self._connect_by_ssid(s, sec))
            self._table.setCellWidget(idx, 3, btn)

    def _connect_selected(self):
        row = self._table.currentRow()
        if row < 0:
            return
        sorted_nets = sorted(self._networks, key=lambda n: -n.signal)
        if row >= len(sorted_nets):
            return
        net = sorted_nets[row]
        self._connect_by_ssid(net.ssid, net.security)

    def _connect_by_ssid(self, ssid: str, security: str):
        if security and security.lower() not in ("none", "--", "open", ""):
            dlg = PasswordDialog(ssid, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            password = dlg.password()
        else:
            password = ""
        self._status_lbl.setText(f"Connecting to {ssid}…")
        self._status_lbl.setStyleSheet("font-size:13px; font-weight:600; color:#f0ad4e;")
        ok, msg = connect_wifi(ssid, password)
        if ok:
            self._start_scan()
        else:
            self._error_lbl.setText(f"⚠  {msg or 'Connection failed. Check credentials.'}")
            self._start_scan()

    def _disconnect(self):
        ok, msg = disconnect_wifi()
        if not ok:
            self._error_lbl.setText(f"⚠  {msg}")
        else:
            self._error_lbl.clear()
        self._start_scan()
