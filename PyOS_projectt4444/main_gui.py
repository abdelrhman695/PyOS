"""
Main GUI — PyOS Desktop Environment v2
Full hybrid macOS/Windows 11/Linux desktop.
Accepts current_user (PyUser) from the login screen.
"""

import os
import math
import platform
from typing import Dict, List, Optional

import psutil
from PyQt6.QtCore import (
    Qt, QTimer, QDateTime, QPropertyAnimation, QEasingCurve,
    QPoint, QSize, pyqtSignal, QRect
)
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QLinearGradient, QRadialGradient, QBrush, QPen,
    QPixmap, QKeyEvent, QImage
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QMdiArea, QMdiSubWindow,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QSplitter, QGroupBox, QTextEdit,
    QLineEdit, QGraphicsOpacityEffect, QMenu, QSizePolicy,
    QGridLayout, QCheckBox, QInputDialog,
)

from process_manager import ProcessManager
from memory_manager import MemoryManager
from io_manager import IOManager
from system_monitor import SystemMonitor
from network import NetworkManager
from terminal import MultiTabTerminal
from browser import BrowserWidget
from file_system import FileManagerWidget
from animated_background import AnimatedBackground
from wifi_manager import WifiManagerWidget
from settings import SettingsWidget
from settings_manager import get_settings, SettingsManager
from themes import build_stylesheet
from user_manager import get_user_manager
from dock import Dock, DockIcon  # Polished futuristic dock (drop-in replacement)


def _c(dark_val: str, light_val: str) -> str:
    sm = get_settings()
    return light_val if sm.get("theme") == "light" else dark_val


# ══════════════════════════════════════════════════════════════════
# Notification Toast
# ══════════════════════════════════════════════════════════════════

class NotificationToast(QWidget):
    dismissed = pyqtSignal()

    _KIND_CFG = {
        "info":    ("#1f6feb", "🔵"),
        "success": ("#2ea043", "✅"),
        "warning": ("#9e6a03", "⚠️"),
        "error":   ("#da3633", "❌"),
    }

    def __init__(self, title, message, kind="info", parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(330, 70)
        color, icon = self._KIND_CFG.get(kind, self._KIND_CFG["info"])
        self._border_color = color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet("font-size:20px; background:transparent;")
        layout.addWidget(lbl_icon)
        col = QVBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color:#fff; font-weight:700; font-size:12px; background:transparent;")
        lbl_msg = QLabel(message)
        lbl_msg.setStyleSheet("color:#c9d1d9; font-size:11px; background:transparent;")
        lbl_msg.setWordWrap(True)
        col.addWidget(lbl_title)
        col.addWidget(lbl_msg)
        layout.addLayout(col, 1)
        close = QPushButton("×")
        close.setFixedSize(18, 18)
        close.setStyleSheet(
            "QPushButton{background:transparent;color:#8b949e;border:none;font-size:15px;}"
            "QPushButton:hover{color:#fff;}"
        )
        close.clicked.connect(self._dismiss)
        layout.addWidget(close)
        self._eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._eff)
        self._eff.setOpacity(0)
        self._fade_in = QPropertyAnimation(self._eff, b"opacity")
        self._fade_in.setDuration(250)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(0.95)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in.start()
        QTimer.singleShot(4500, self._dismiss)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(22, 27, 34, 235)))
        p.setPen(QPen(QColor(self._border_color), 1.5))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

    def _dismiss(self):
        anim = QPropertyAnimation(self._eff, b"opacity")
        anim.setDuration(250)
        anim.setEndValue(0.0)
        anim.finished.connect(self.close)
        anim.finished.connect(self.dismissed)
        anim.start()
        self._fade_out = anim


class NotificationCenter:
    def __init__(self, parent: QWidget):
        self._parent = parent
        self._toasts: List[NotificationToast] = []

    def notify(self, title, message, kind="info"):
        t = NotificationToast(title, message, kind, self._parent)
        t.dismissed.connect(lambda: self._remove(t))
        self._toasts.append(t)
        self._restack()
        t.show()
        t.raise_()

    def _remove(self, t):
        if t in self._toasts:
            self._toasts.remove(t)
        self._restack()

    def _restack(self):
        pw = self._parent.width()
        for i, t in enumerate(self._toasts):
            t.move(pw - t.width() - 14, 50 + i * (t.height() + 6))
            t.raise_()


class DesktopIcon(QWidget):
    def __init__(self, emoji, label, cb, parent=None):
        super().__init__(parent)
        self._cb = cb; self._hover = False
        self.setFixedSize(76, 76)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        e = QLabel(emoji)
        e.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e.setStyleSheet("font-size:28px; background:transparent;")
        lay.addWidget(e)
        l = QLabel(label)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.setWordWrap(True)
        l.setStyleSheet("color:#fff; font-size:10px; background:transparent;")
        lay.addWidget(l)

    def mousePressEvent(self, e): self._cb()
    def mouseDoubleClickEvent(self, e): self._cb()
    def enterEvent(self, e): self._hover = True; self.update()
    def leaveEvent(self, e): self._hover = False; self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            p.setBrush(QBrush(QColor(255, 255, 255, 26)))
            p.setPen(QPen(QColor(255, 255, 255, 45), 1))
            p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)
        super().paintEvent(e)


def _tbl(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    return t


# ══════════════════════════════════════════════════════════════════
# App sub-windows
# ══════════════════════════════════════════════════════════════════

class TaskManagerWindow(QWidget):
    def __init__(self, mgr: ProcessManager, parent=None):
        super().__init__(parent)
        self._mgr = mgr
        self._build()
        QTimer(self, timeout=self._refresh, interval=1500).start()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self._tabs = QTabWidget()
        sim = QWidget(); sl = QVBoxLayout(sim)
        row = QHBoxLayout()
        self._name_in = QLineEdit()
        self._name_in.setPlaceholderText("Process name…")
        row.addWidget(self._name_in)
        spawn = QPushButton("+ Spawn"); spawn.setProperty("primary", True)
        spawn.clicked.connect(self._spawn); row.addWidget(spawn)
        sl.addLayout(row)
        self._sim_tbl = _tbl(["PID", "Name", "State", "CPU %", "Mem MB", "Priority"])
        self._sim_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._sim_tbl.customContextMenuRequested.connect(self._ctx)
        sl.addWidget(self._sim_tbl)
        self._tabs.addTab(sim, "Simulated Processes")
        real = QWidget(); rl = QVBoxLayout(real)
        self._real_tbl = _tbl(["PID", "Name", "State", "CPU %", "Mem MB"])
        rl.addWidget(self._real_tbl)
        self._tabs.addTab(real, "Real System Processes")
        lay.addWidget(self._tabs)

    def _spawn(self):
        name = self._name_in.text().strip() or "process"
        self._mgr.create_process(name); self._name_in.clear()

    def _ctx(self, pos):
        row = self._sim_tbl.currentRow()
        if row < 0: return
        pid_item = self._sim_tbl.item(row, 0)
        if not pid_item: return
        pid = int(pid_item.text())
        m = QMenu(self)
        m.addAction("Terminate").triggered.connect(lambda: self._mgr.terminate_process(pid))
        m.exec(self._sim_tbl.mapToGlobal(pos))

    def _refresh(self):
        self._fill(self._sim_tbl, self._mgr.get_all(), True)
        if self._tabs.currentIndex() == 1:
            self._fill(self._real_tbl, self._mgr.get_real_processes(), False)

    def _fill(self, table, rows, sim):
        SC = {"Running": "#3fb950", "Ready": "#58a6ff", "Waiting": "#f0ad4e", "Terminated": "#f85149"}
        table.setRowCount(0)
        for r in rows:
            i = table.rowCount(); table.insertRow(i)
            state = r.get("state", "")
            def cell(v, col, c=None):
                item = QTableWidgetItem(str(v))
                if c: item.setForeground(QColor(c))
                table.setItem(i, col, item)
            cell(r["pid"], 0); cell(r["name"], 1)
            cell(state, 2, SC.get(state)); cell(r["cpu_usage"], 3)
            cell(r["memory_mb"], 4)
            if sim: cell(r.get("priority", ""), 5)


class MemoryViewWindow(QWidget):
    BLOCK = 32

    def __init__(self, mgr: MemoryManager, parent=None):
        super().__init__(parent)
        self._mgr = mgr
        self._build()
        QTimer(self, timeout=self._refresh, interval=2000).start()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10)
        stats = QGroupBox("Statistics"); sl = QHBoxLayout(stats)
        self._total = QLabel(); self._used = QLabel()
        self._free = QLabel(); self._bar = QProgressBar()
        for w in (self._total, self._used, self._free): sl.addWidget(w)
        sl.addWidget(self._bar, 1); lay.addWidget(stats)
        grp = QGroupBox("Memory Map  (each block = 32 MB)"); gl = QVBoxLayout(grp)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._map_w = QWidget()
        self._grid = QGridLayout(self._map_w); self._grid.setSpacing(2)
        scroll.setWidget(self._map_w); gl.addWidget(scroll); lay.addWidget(grp, 1)

    def _refresh(self):
        s = self._mgr.stats()
        self._total.setText(f"Total: {s['total_mb']} MB")
        self._used.setText(f"Used: {s['used_mb']} MB")
        self._free.setText(f"Free: {s['free_mb']} MB")
        self._bar.setValue(int(s['used_pct']))
        blocks = self._mgr.get_map()
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for i, b in enumerate(blocks):
            c = QLabel(); c.setFixedSize(self.BLOCK, self.BLOCK)
            c.setToolTip(f"Block {b['index']}" + (f"\nPID {b['pid']}: {b['process_name']}" if b['allocated'] else "\nFree"))
            bg = "#2ea043" if b['allocated'] else "#21262d"
            c.setStyleSheet(f"background:{bg};border-radius:3px;border:1px solid rgba(255,255,255,0.04);")
            self._grid.addWidget(c, i // 16, i % 16)


class SystemMonitorWindow(QWidget):
    def __init__(self, mon: SystemMonitor, parent=None):
        super().__init__(parent)
        self._core_bars: list = []
        self._build()
        mon.statsUpdated.connect(self._update)

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 10, 10, 10); lay.setSpacing(10)

        def grp(title):
            g = QGroupBox(title); gl = QVBoxLayout(g); return g, gl

        def bar(label, parent_lay):
            parent_lay.addWidget(QLabel(label))
            b = QProgressBar(); b.setRange(0, 100); b.setTextVisible(True); b.setFormat("%v%")
            parent_lay.addWidget(b); return b

        cpu_grp, cl = grp("CPU")
        self._cpu_bar = bar("Total", cl)
        self._cpu_info = QLabel(); self._cpu_info.setStyleSheet("font-size:11px; color:#6e7681;")
        cl.addWidget(self._cpu_info)
        self._core_ctr = QWidget()
        self._core_grid = QGridLayout(self._core_ctr); self._core_grid.setSpacing(4)
        cl.addWidget(self._core_ctr); lay.addWidget(cpu_grp)

        mem_grp, ml = grp("Memory")
        self._mem_bar = bar("RAM", ml)
        self._mem_lbl = QLabel(); self._mem_lbl.setStyleSheet("font-size:11px; color:#6e7681;")
        ml.addWidget(self._mem_lbl)
        self._swap_bar = bar("Swap", ml); lay.addWidget(mem_grp)

        disk_grp, dl = grp("Disk  (/)")
        self._disk_bar = bar("Usage", dl)
        self._disk_lbl = QLabel(); self._disk_lbl.setStyleSheet("font-size:11px; color:#6e7681;")
        dl.addWidget(self._disk_lbl); lay.addWidget(disk_grp)

        net_grp, nl = grp("Network I/O")
        self._net_lbl = QLabel(); nl.addWidget(self._net_lbl)
        lay.addWidget(net_grp); lay.addStretch()

    def _update(self, s):
        cpu = s["cpu"]
        self._cpu_bar.setValue(int(cpu["total_pct"]))
        self._cpu_info.setText(f"{cpu['count_logical']} logical | {cpu['count_physical']} physical | {cpu['freq_mhz']:.0f} MHz")
        cores = cpu["cores"]
        if len(self._core_bars) != len(cores):
            while self._core_grid.count():
                item = self._core_grid.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            self._core_bars.clear()
            for i, c in enumerate(cores):
                cont = QWidget(); cl2 = QVBoxLayout(cont); cl2.setSpacing(1); cl2.setContentsMargins(0,0,0,0)
                lbl = QLabel(f"C{c['core']}"); lbl.setStyleSheet("font-size:9px;color:#6e7681;"); lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                b = QProgressBar(); b.setRange(0,100); b.setTextVisible(False); b.setFixedHeight(10)
                cl2.addWidget(lbl); cl2.addWidget(b); self._core_bars.append(b)
                self._core_grid.addWidget(cont, i // 4, i % 4)
        for b, c in zip(self._core_bars, cores):
            b.setValue(int(c["pct"]))
        m = s["memory"]
        self._mem_bar.setValue(int(m["pct"]))
        self._mem_lbl.setText(f"{m['used_gb']:.2f} / {m['total_gb']:.2f} GB")
        self._swap_bar.setValue(int(m["swap_pct"]))
        d = s["disk"]
        self._disk_bar.setValue(int(d["pct"]))
        self._disk_lbl.setText(f"{d['used_gb']:.1f} / {d['total_gb']:.1f} GB")
        n = s["network"]
        self._net_lbl.setText(f"↑ {n['bytes_sent_mb']:.1f} MB  ·  ↓ {n['bytes_recv_mb']:.1f} MB")


class NetworkWindow(QWidget):
    def __init__(self, mgr: NetworkManager, parent=None):
        super().__init__(parent)
        self._mgr = mgr; self._build()
        mgr.infoReady.connect(self._upd_info)
        mgr.hostFound.connect(self._add_host)
        mgr.scanFinished.connect(self._scan_done)
        mgr.probe_latency()

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(10,10,10,10); lay.setSpacing(8)
        info = QGroupBox("Connection Information"); il = QVBoxLayout(info)
        self._info_lbl = QLabel("Detecting…"); il.addWidget(self._info_lbl)
        lat_row = QHBoxLayout(); self._lat: Dict[str, QLabel] = {}
        for h in ["1.1.1.1", "8.8.8.8"]:
            l = QLabel(f"{h}: probing…"); l.setStyleSheet("font-size:12px;")
            lat_row.addWidget(l); self._lat[h] = l
        il.addLayout(lat_row); lay.addWidget(info)
        scan = QGroupBox("Local Network Scanner  (IP · MAC · Hostname)"); sl = QVBoxLayout(scan)
        br = QHBoxLayout()
        self._scan_btn = QPushButton("🔍  Scan Network"); self._scan_btn.setProperty("primary", True)
        self._scan_btn.clicked.connect(self._start); br.addWidget(self._scan_btn)
        self._scan_st = QLabel(""); self._scan_st.setStyleSheet("font-size:11px;color:#6e7681;")
        br.addWidget(self._scan_st); br.addStretch(); sl.addLayout(br)
        self._host_tbl = _tbl(["IP Address", "MAC Address", "Hostname", "Latency (ms)"])
        sl.addWidget(self._host_tbl); lay.addWidget(scan, 1)

    def _upd_info(self, info):
        self._info_lbl.setText(f"Local IP: {info['local_ip']}  ·  Subnet: {info['subnet']}.0/24  ·  Type: {info['connection_type']}")
        for h, lbl in self._lat.items():
            ms = info["latencies"].get(h, -1)
            if ms < 0: lbl.setText(f"{h}: timeout"); lbl.setStyleSheet("color:#f85149;font-size:12px;")
            else: lbl.setText(f"{h}: {ms:.1f} ms"); lbl.setStyleSheet("color:#3fb950;font-size:12px;")

    def _start(self):
        self._host_tbl.setRowCount(0); self._scan_btn.setEnabled(False)
        self._scan_st.setText("Scanning…"); self._mgr.start_scan()

    def _add_host(self, e):
        i = self._host_tbl.rowCount(); self._host_tbl.insertRow(i)
        self._host_tbl.setItem(i, 0, QTableWidgetItem(e["ip"]))
        self._host_tbl.setItem(i, 1, QTableWidgetItem(e.get("mac") or "—"))
        self._host_tbl.setItem(i, 2, QTableWidgetItem(e.get("hostname","") or ""))
        ms = QTableWidgetItem(str(e["latency_ms"])); ms.setForeground(QColor("#3fb950"))
        self._host_tbl.setItem(i, 3, ms)

    def _scan_done(self, results):
        self._scan_btn.setEnabled(True)
        self._scan_st.setText(f"Found {len(results)} device(s)")


class IOManagerWindow(QWidget):
    def __init__(self, io: IOManager, parent=None):
        super().__init__(parent)
        self._build()
        io.devicesUpdated.connect(self._upd)

    def _build(self):
        lay = QVBoxLayout(self); lay.setContentsMargins(10,10,10,10)
        self._tbl = _tbl(["Device", "Type", "State", "Current Value", "Queue Depth"])
        self._tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self._tbl)

    def _upd(self, devs):
        SC = {"Available": "#3fb950", "Busy": "#f0ad4e", "Offline": "#f85149"}
        self._tbl.setRowCount(0)
        for d in devs:
            i = self._tbl.rowCount(); self._tbl.insertRow(i)
            self._tbl.setItem(i, 0, QTableWidgetItem(d["name"]))
            self._tbl.setItem(i, 1, QTableWidgetItem(d["type"]))
            si = QTableWidgetItem(d["state"]); si.setForeground(QColor(SC.get(d["state"],"#c0caf5")))
            self._tbl.setItem(i, 2, si)
            self._tbl.setItem(i, 3, QTableWidgetItem(d["value"]))
            qi = QTableWidgetItem(str(d["queue"])); qi.setForeground(QColor("#f0ad4e" if d["queue"] else "#6e7681"))
            self._tbl.setItem(i, 4, qi)


# ══════════════════════════════════════════════════════════════════
# User Manager Window (new)
# ══════════════════════════════════════════════════════════════════

class UserManagerWindow(QWidget):
    """GUI for managing PyOS users and groups — mirrors terminal commands."""

    def __init__(self, current_user=None, parent=None):
        super().__init__(parent)
        self._current_user = current_user
        self._um = get_user_manager()
        self._build()
        self._refresh()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self._tabs = QTabWidget()

        # ── Users tab ──
        users_w = QWidget(); ul = QVBoxLayout(users_w); ul.setContentsMargins(8,8,8,8)

        create_grp = QGroupBox("Create New User")
        cl = QVBoxLayout(create_grp)
        row1 = QHBoxLayout()
        self._new_user  = QLineEdit(); self._new_user.setPlaceholderText("Username")
        self._new_pw    = QLineEdit(); self._new_pw.setPlaceholderText("Password"); self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_groups = QLineEdit(); self._new_groups.setPlaceholderText("Groups (comma separated, optional)")
        row1.addWidget(QLabel("User:")); row1.addWidget(self._new_user)
        row1.addWidget(QLabel("Password:")); row1.addWidget(self._new_pw)
        cl.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Groups:")); row2.addWidget(self._new_groups, 1)
        self._admin_chk = QCheckBox("Admin (sudo)")
        row2.addWidget(self._admin_chk)
        btn_create_user = QPushButton("+ Create User"); btn_create_user.setProperty("primary", True)
        btn_create_user.clicked.connect(self._create_user); row2.addWidget(btn_create_user)
        cl.addLayout(row2)
        ul.addWidget(create_grp)

        self._user_tbl = _tbl(["UID", "Username", "Groups", "Shell", "Admin"])
        self._user_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        ul.addWidget(self._user_tbl, 1)

        user_actions = QHBoxLayout()
        btn_del_user = QPushButton("🗑 Delete Selected User")
        btn_del_user.clicked.connect(self._delete_user); user_actions.addWidget(btn_del_user)
        btn_chpw = QPushButton("🔑 Change Password")
        btn_chpw.clicked.connect(self._change_password); user_actions.addWidget(btn_chpw)
        user_actions.addStretch()
        ul.addLayout(user_actions)

        self._tabs.addTab(users_w, "👤  Users")

        # ── Groups tab ──
        groups_w = QWidget(); gl = QVBoxLayout(groups_w); gl.setContentsMargins(8,8,8,8)

        grp_create = QGroupBox("Create New Group")
        gcl = QHBoxLayout(grp_create)
        self._new_group = QLineEdit(); self._new_group.setPlaceholderText("Group name")
        btn_create_grp  = QPushButton("+ Create Group"); btn_create_grp.setProperty("primary", True)
        btn_create_grp.clicked.connect(self._create_group)
        gcl.addWidget(QLabel("Name:")); gcl.addWidget(self._new_group, 1); gcl.addWidget(btn_create_grp)
        gl.addWidget(grp_create)

        self._group_tbl = _tbl(["GID", "Group Name", "Members"])
        self._group_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        gl.addWidget(self._group_tbl, 1)

        grp_actions = QHBoxLayout()
        btn_del_grp = QPushButton("🗑 Delete Selected Group")
        btn_del_grp.clicked.connect(self._delete_group); grp_actions.addWidget(btn_del_grp)
        grp_actions.addStretch()
        gl.addLayout(grp_actions)

        self._tabs.addTab(groups_w, "👥  Groups")

        lay.addWidget(self._tabs)

        self._status = QLabel("")
        self._status.setStyleSheet("font-size:11px; color:#8b949e; padding:2px 4px;")
        lay.addWidget(self._status)

    def _is_admin(self):
        if not self._current_user: return True
        return self._um.is_admin(self._current_user.username)

    def _set_status(self, msg, ok=True):
        color = "#3fb950" if ok else "#f85149"
        self._status.setStyleSheet(f"font-size:11px; color:{color}; padding:2px 4px;")
        self._status.setText(msg)

    def _refresh(self):
        self._user_tbl.setRowCount(0)
        for u in self._um.list_users():
            i = self._user_tbl.rowCount(); self._user_tbl.insertRow(i)
            self._user_tbl.setItem(i, 0, QTableWidgetItem(str(u.uid)))
            self._user_tbl.setItem(i, 1, QTableWidgetItem(u.username))
            self._user_tbl.setItem(i, 2, QTableWidgetItem(", ".join(u.groups)))
            self._user_tbl.setItem(i, 3, QTableWidgetItem(u.shell))
            adm = QTableWidgetItem("✓" if u.is_admin else "")
            adm.setForeground(QColor("#3fb950" if u.is_admin else "#6e7681"))
            self._user_tbl.setItem(i, 4, adm)

        self._group_tbl.setRowCount(0)
        for g in self._um.list_groups():
            i = self._group_tbl.rowCount(); self._group_tbl.insertRow(i)
            self._group_tbl.setItem(i, 0, QTableWidgetItem(str(g.gid)))
            self._group_tbl.setItem(i, 1, QTableWidgetItem(g.groupname))
            self._group_tbl.setItem(i, 2, QTableWidgetItem(", ".join(g.members)))

    def _create_user(self):
        if not self._is_admin():
            self._set_status("Permission denied: requires admin.", ok=False); return
        username = self._new_user.text().strip()
        password = self._new_pw.text()
        raw_grps = self._new_groups.text().strip()
        groups   = [g.strip() for g in raw_grps.split(",") if g.strip()] if raw_grps else []
        is_admin = self._admin_chk.isChecked()
        if is_admin and "sudo" not in groups:
            groups.append("sudo")
        ok, msg = self._um.create_user(username, password, groups=groups, is_admin=is_admin)
        self._set_status(msg, ok)
        if ok:
            self._new_user.clear(); self._new_pw.clear()
            self._new_groups.clear(); self._admin_chk.setChecked(False)
            self._refresh()

    def _delete_user(self):
        if not self._is_admin():
            self._set_status("Permission denied: requires admin.", ok=False); return
        row = self._user_tbl.currentRow()
        if row < 0: self._set_status("Select a user first.", ok=False); return
        uname = self._user_tbl.item(row, 1).text()
        ok, msg = self._um.delete_user(uname)
        self._set_status(msg, ok)
        if ok: self._refresh()

    def _change_password(self):
        row = self._user_tbl.currentRow()
        if row < 0: self._set_status("Select a user first.", ok=False); return
        uname = self._user_tbl.item(row, 1).text()
        if not self._is_admin() and (self._current_user and uname != self._current_user.username):
            self._set_status("Permission denied: can only change your own password.", ok=False); return
        new_pw, ok = QInputDialog.getText(self, "Change Password",
                                          f"New password for '{uname}':",
                                          QLineEdit.EchoMode.Password)
        if ok and new_pw:
            ok2, msg = self._um.change_password(uname, new_pw)
            self._set_status(msg, ok2)

    def _create_group(self):
        if not self._is_admin():
            self._set_status("Permission denied: requires admin.", ok=False); return
        name = self._new_group.text().strip()
        ok, msg = self._um.create_group(name)
        self._set_status(msg, ok)
        if ok: self._new_group.clear(); self._refresh()

    def _delete_group(self):
        if not self._is_admin():
            self._set_status("Permission denied: requires admin.", ok=False); return
        row = self._group_tbl.currentRow()
        if row < 0: self._set_status("Select a group first.", ok=False); return
        gname = self._group_tbl.item(row, 1).text()
        ok, msg = self._um.delete_group(gname)
        self._set_status(msg, ok)
        if ok: self._refresh()


# ══════════════════════════════════════════════════════════════════
# Main Window
# ══════════════════════════════════════════════════════════════════

class _TopBar(QWidget):
    """
    Premium glassmorphism top bar with animated stat pills,
    user badge, and live clock.
    """

    def __init__(self, current_user=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("topbar")

        # Expose labels so MainWindow can update them
        self.cpu_lbl   = QLabel("CPU  0%")
        self.ram_lbl   = QLabel("RAM  0%")
        self.clock_lbl = QLabel()

        self._pulse_t = 0.0
        self._pulse_timer = QTimer(self, interval=33)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_timer.start()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 18, 0)
        lay.setSpacing(0)

        # ── Logo ──────────────────────────────────────────────────
        logo = QLabel("  Py<span style='color:#7aa2f7;'>OS</span>")
        logo.setTextFormat(Qt.TextFormat.RichText)
        logo.setStyleSheet(
            "font-size:15px; font-weight:800; color:white;"
            "letter-spacing:-0.5px; background:transparent;"
            "font-family: 'SF Pro Display','Segoe UI',sans-serif;"
        )
        lay.addWidget(logo)
        lay.addStretch()

        # ── Stat pills ────────────────────────────────────────────
        pill_style = (
            "background: rgba(255,255,255,0.07);"
            "border: 1px solid rgba(255,255,255,0.12);"
            "border-radius: 10px;"
            "padding: 2px 10px;"
            "font-size: 11px;"
            "color: rgba(180, 200, 255, 0.85);"
            "font-family: 'JetBrains Mono','Consolas','Courier New',monospace;"
        )
        for lbl in (self.cpu_lbl, self.ram_lbl):
            lbl.setStyleSheet(pill_style)
            lbl.setFixedHeight(22)
            lay.addWidget(lbl)
            lay.addSpacing(6)

        # ── User badge ────────────────────────────────────────────
        if current_user:
            uname  = current_user.username
            is_adm = current_user.is_admin
            badge  = "⚡" if is_adm else "●"
            badge_color = "#f7c948" if is_adm else "#7ee787"
            user_lbl = QLabel(f"<span style='color:{badge_color}'>{badge}</span>  {uname}")
            user_lbl.setTextFormat(Qt.TextFormat.RichText)
            user_lbl.setStyleSheet(
                "font-size:11px; color:rgba(220,230,255,0.88);"
                "background: rgba(255,255,255,0.06);"
                "border: 1px solid rgba(255,255,255,0.10);"
                "border-radius: 10px;"
                "padding: 2px 12px;"
                "font-family: 'Segoe UI',sans-serif;"
            )
            user_lbl.setFixedHeight(22)
            lay.addWidget(user_lbl)
            lay.addSpacing(12)

        # ── Clock ─────────────────────────────────────────────────
        self.clock_lbl.setStyleSheet(
            "font-size:12px; font-weight:600;"
            "color:rgba(255,255,255,0.92);"
            "background:transparent;"
            "font-family: 'Segoe UI','SF Pro Display',sans-serif;"
            "letter-spacing: 0.2px;"
        )
        lay.addWidget(self.clock_lbl)

    def _pulse_tick(self):
        self._pulse_t = (self._pulse_t + 0.04) % (2 * math.pi)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # ── Multi-layer glass background ──────────────────────────
        # Main fill
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(10, 8, 26, 200))
        grad.setColorAt(0.5, QColor(8,  6, 20, 210))
        grad.setColorAt(1.0, QColor(6,  4, 16, 220))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(0, 0, w, h)

        # Top-edge shimmer line
        shimmer_alpha = int(30 + 12 * math.sin(self._pulse_t))
        p.setPen(QPen(QColor(140, 170, 255, shimmer_alpha), 1))
        p.drawLine(0, 0, w, 0)

        # Inner top highlight
        shine = QLinearGradient(0, 0, 0, h * 0.6)
        shine.setColorAt(0.0, QColor(255, 255, 255, 14))
        shine.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(shine))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(0, 0, w, h)

        # Bottom separator — subtle glow line
        sep_alpha = int(35 + 15 * math.sin(self._pulse_t * 0.7))
        sep_grad = QLinearGradient(0, h - 1, w, h - 1)
        sep_grad.setColorAt(0.0,  QColor(60, 100, 255, 0))
        sep_grad.setColorAt(0.2,  QColor(100, 150, 255, sep_alpha))
        sep_grad.setColorAt(0.5,  QColor(140, 180, 255, sep_alpha + 15))
        sep_grad.setColorAt(0.8,  QColor(100, 150, 255, sep_alpha))
        sep_grad.setColorAt(1.0,  QColor(60,  100, 255, 0))
        p.setPen(QPen(QBrush(sep_grad), 1))
        p.drawLine(0, h - 1, w, h - 1)


class _SafeBrowserWrapper(QWidget):
    """
    Thin wrapper around BrowserWidget that guarantees cleanup()
    is called on all tabs before Qt's WA_DeleteOnClose destroys
    the QWebEngineView children — otherwise the app crashes.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        from browser import BrowserWidget
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._bw = BrowserWidget(self)
        lay.addWidget(self._bw)

    def closeEvent(self, event):
        # Cleanup all WebEngine tabs before Qt destroys the widget tree
        try:
            self._bw.closeEvent(event)
        except Exception:
            pass
        super().closeEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, current_user=None):
        super().__init__()
        self._current_user = current_user
        username = current_user.username if current_user else "user"

        self.setWindowTitle("PyOS")
        self.showFullScreen()

        self._sm: SettingsManager = get_settings()
        self._open_windows: Dict[str, QMdiSubWindow] = {}

        self._proc_mgr = ProcessManager()
        self._mem_mgr  = MemoryManager()
        self._io_mgr   = IOManager(self)
        self._monitor  = SystemMonitor(self._sm.get("monitor_interval_ms", 2000), self)
        self._net_mgr  = NetworkManager(self)

        for name in ["init", "kernel", "syslogd", "networkd", "udevd"]:
            p = self._proc_mgr.create_process(name, priority=8)
            self._mem_mgr.allocate(p.pid, name, p.memory_mb)
        self._proc_mgr.start()
        self._monitor.start()

        self._build_ui()
        self._notif = NotificationCenter(self)
        self._apply_theme()
        self._sm.subscribe("*", self._on_setting)

        self._io_timer = QTimer(self, interval=400)
        self._io_timer.timeout.connect(lambda: self._io_mgr.on_mouse_move(
            self.mapFromGlobal(self.cursor().pos()).x(),
            self.mapFromGlobal(self.cursor().pos()).y()
        ))
        self._io_timer.start()

        QTimer.singleShot(80, lambda: self.resizeEvent(None))
        QTimer.singleShot(900, lambda: self._notif.notify(
            "PyOS Ready", f"Welcome, {username}! Click dock icons to launch apps.", "success"
        ))

    def _apply_theme(self):
        theme  = self._sm.get("theme", "dark")
        accent = self._sm.get("accent_color", "#0078d4")
        QApplication.instance().setStyleSheet(build_stylesheet(theme, accent))
        if hasattr(self, "_bg"):
            self._bg.set_theme(theme, accent)

    def _on_setting(self, key, value):
        if key in ("theme", "accent_color"):
            self._apply_theme()
        elif key == "background_style":
            img = self._sm.get("background_image", "")
            if not img: self._bg.set_style(value)
        elif key == "background_image":
            if value: self._bg._anim_timer.stop()
            else:
                if self._sm.get("animations_enabled", True):
                    self._bg._anim_timer.start(33)
                    self._bg.set_style(self._sm.get("background_style", "Aurora"))
            self._bg.update()
        elif key == "animations_enabled":
            if value: self._bg._anim_timer.start(33)
            else: self._bg._anim_timer.stop(); self._bg.update()
        self._notif.notify("Settings", f"{key} updated", "info")

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        self._bg = AnimatedBackground(central)
        self._bg.lower()
        self._bg.set_style(self._sm.get("background_style", "Aurora"))
        self._bg.set_theme(self._sm.get("theme", "dark"), self._sm.get("accent_color", "#0078d4"))

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        topbar = _TopBar(self._current_user, parent=central)
        topbar.setFixedHeight(42)
        self._cpu_lbl = topbar.cpu_lbl
        self._ram_lbl = topbar.ram_lbl
        self._clock_lbl = topbar.clock_lbl
        root.addWidget(topbar)

        self._mdi = QMdiArea()
        self._mdi.setBackground(QColor(0, 0, 0, 0))
        self._mdi.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        root.addWidget(self._mdi, 1)

        self._icon_col = QWidget(self._mdi.viewport())
        self._icon_col.setFixedWidth(94)
        self._icon_col.setStyleSheet("background: transparent;")
        self._build_icon_column()
        self._icon_col.show()

        dock_wrap = QWidget(); dock_wrap.setFixedHeight(112)
        dock_wrap.setStyleSheet("background:transparent;")
        dw_lay = QHBoxLayout(dock_wrap)
        dw_lay.setContentsMargins(0, 4, 0, 8)
        dw_lay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self._dock = Dock()
        self._build_dock()
        dw_lay.addWidget(self._dock)
        root.addWidget(dock_wrap)

        self._clock_timer = QTimer(self, interval=1000)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start()
        self._update_clock()
        self._monitor.statsUpdated.connect(self._update_tray)

    def _build_dock(self):
        apps = [
            ("💻", "Terminal",      self.open_terminal),
            ("🌐", "Browser",       self.open_browser),
            ("📁", "Files",         self.open_files),
            ("📊", "Task Manager",  self.open_tasks),
            ("📡", "Network",       self.open_network),
            ("📶", "Wi-Fi",         self.open_wifi),
        ]
        for emoji, label, cb in apps:
            self._dock.add_icon(emoji, label, cb)

        apps2 = [
            ("🎮", "I/O Manager",    self.open_io),
            ("🖥️", "System Monitor", self.open_monitor),
            ("🧠", "Memory",         self.open_memory),
            ("👥", "Users",          self.open_users),
            ("⚙️", "Settings",       self.open_settings),
        ]
        for i, (emoji, label, cb) in enumerate(apps2):
            self._dock.add_icon(emoji, label, cb, with_separator=(i == 0))

    def _build_icon_column(self):
        lay = QVBoxLayout(self._icon_col)
        lay.setContentsMargins(10, 16, 4, 8)
        lay.setSpacing(4)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        for emoji, label, cb in [
            ("💻", "Terminal",  self.open_terminal),
            ("🌐", "Browser",   self.open_browser),
            ("📁", "Files",     self.open_files),
            ("👥", "Users",     self.open_users),
            ("⚙️", "Settings",  self.open_settings),
        ]:
            lay.addWidget(DesktopIcon(emoji, label, cb, self._icon_col))
        lay.addStretch()

    def _update_clock(self):
        dt = QDateTime.currentDateTime()
        self._clock_lbl.setText(dt.toString("  hh:mm  ·  ddd d MMM  "))

    def _update_tray(self, s):
        cpu_pct = s['cpu']['total_pct']
        ram_pct = s['memory']['pct']

        # Color-code by load level
        def _pill_color(pct):
            if pct < 50:  return "rgba(180, 210, 255, 0.85)"
            if pct < 80:  return "rgba(250, 200, 80, 0.90)"
            return "rgba(255, 110, 110, 0.95)"

        _base_pill = (
            "background: rgba(255,255,255,0.07);"
            "border: 1px solid rgba(255,255,255,0.12);"
            "border-radius: 10px; padding: 2px 10px;"
            "font-size: 11px;"
            "font-family: 'JetBrains Mono','Consolas','Courier New',monospace;"
        )
        self._cpu_lbl.setStyleSheet(_base_pill + f"color: {_pill_color(cpu_pct)};")
        self._ram_lbl.setStyleSheet(_base_pill + f"color: {_pill_color(ram_pct)};")
        self._cpu_lbl.setText(f"CPU  {cpu_pct:.0f}%")
        self._ram_lbl.setText(f"RAM  {ram_pct:.0f}%")

        if self._sm.get("auto_optimize") and cpu_pct > 80:
            self._bg._anim_timer.setInterval(100)
        elif self._sm.get("animations_enabled", True):
            self._bg._anim_timer.setInterval(33)

    def resizeEvent(self, event):
        if hasattr(self, "_bg"):
            self._bg.setGeometry(self.centralWidget().rect())
        if hasattr(self, "_icon_col"):
            mdi_h = self._mdi.height()
            self._icon_col.setGeometry(0, 0, 94, mdi_h)
        if event:
            super().resizeEvent(event)

    def _open_win(self, key, title, widget, w=900, h=600):
        if key in self._open_windows:
            sub = self._open_windows[key]
            if sub is not None and not sub.isHidden():
                sub.raise_(); sub.activateWindow()
                self._dock.set_active(key, True); return sub

        sub = QMdiSubWindow()
        sub.setWidget(widget)
        sub.setWindowTitle(title)
        sub.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        sub.resize(w, h)
        self._mdi.addSubWindow(sub)
        sub.show()

        if hasattr(self, "_icon_col"):
            self._icon_col.lower()

        n = len(self._mdi.subWindowList())
        sub.move(100 + n * 22, min(n * 18, 140))
        self._open_windows[key] = sub
        self._dock.set_active(key, True)

        def _on_close():
            self._open_windows.pop(key, None)
            self._dock.set_active(key, False)

        sub.destroyed.connect(_on_close)
        return sub

    # ── App launchers ──────────────────────────────────────────────

    def open_terminal(self):
        uname = self._current_user.username if self._current_user else ""
        self._open_win("Terminal", "💻  Terminal", MultiTabTerminal(current_user=uname), 820, 520)

    def open_browser(self):
        self._open_win("Browser", "🌐  Web Browser", _SafeBrowserWrapper(), 1100, 700)

    def open_files(self):
        self._open_win("Files", "📁  File Manager", FileManagerWidget(), 900, 600)

    def open_tasks(self):
        self._open_win("Task Manager", "📊  Task Manager", TaskManagerWindow(self._proc_mgr), 820, 520)

    def open_network(self):
        self._open_win("Network", "📡  Network Scanner", NetworkWindow(self._net_mgr), 800, 580)

    def open_wifi(self):
        self._open_win("Wi-Fi", "📶  Wi-Fi Manager", WifiManagerWidget(), 700, 500)

    def open_io(self):
        self._open_win("I/O Manager", "🎮  I/O Manager", IOManagerWindow(self._io_mgr), 700, 420)

    def open_monitor(self):
        self._open_win("System Monitor", "🖥️  System Monitor", SystemMonitorWindow(self._monitor), 600, 580)

    def open_memory(self):
        self._open_win("Memory", "🧠  Memory Viewer", MemoryViewWindow(self._mem_mgr), 700, 480)

    def open_users(self):
        self._open_win("Users", "👥  User Manager", UserManagerWindow(self._current_user), 780, 540)

    def open_settings(self):
        self._open_win("Settings", "⚙️  Settings", SettingsWidget(self._sm), 680, 520)

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() == Qt.Key.Key_Escape and e.modifiers() == Qt.KeyboardModifier.NoModifier:
            pass
        else:
            self._io_mgr.on_key_press(str(e.key()))
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        self._io_mgr.on_key_release()
        super().keyReleaseEvent(e)