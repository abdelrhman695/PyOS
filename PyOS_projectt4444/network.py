"""
Network Module — PyOS
Aggressive LAN scanner that works on Windows even when ICMP is blocked.

Scan order (fastest-first):
  1. Gateway      — always alive, detected from routing table instantly
  2. ARP table    — zero network traffic, instant OS cache read
  3. TCP probe    — 15 ports per host, all 254 in parallel threads
  4. Second ARP   — pick up MACs that appeared after TCP handshakes
"""

import subprocess
import socket
import platform
import re
import time
import threading
import ipaddress
from typing import List, Dict, Optional

import psutil
from PyQt6.QtCore import QThread, pyqtSignal, QObject

_SYS = platform.system().lower()

# ── Probe port list — ordered by "most likely open first" ─────────────────
# Port 53 (DNS) is open on virtually EVERY home router.
# Port 80 / 443 — routers, NAS, printers, cameras.
# Ports 445 / 135 / 3389 — Windows devices.
_PROBE_PORTS = (
    53,               # DNS    ← open on ALL routers, guaranteed
    80, 443,          # HTTP/HTTPS
    8080, 8443,       # Alt-HTTP  — NAS, DVR, IoT
    22,               # SSH
    23,               # Telnet
    445, 139, 135,    # SMB / NetBIOS / RPC  (Windows)
    3389,             # RDP  (Windows)
    9100,             # Printer raw
    21,               # FTP
    554,              # RTSP  (IP cameras)
)

_OUI: Dict[str, str] = {
    "00:50:56": "VMware",       "00:0c:29": "VMware",
    "00:15:5d": "Hyper-V",      "00:1a:11": "Google",
    "b8:27:eb": "Raspberry Pi", "dc:a6:32": "Raspberry Pi",
    "e4:5f:01": "Raspberry Pi", "00:17:88": "Philips Hue",
    "00:1e:c2": "Apple",        "3c:22:fb": "Apple",
    "a4:c3:f0": "Apple",        "98:01:a7": "Apple",
    "00:23:14": "Dell",         "18:66:da": "Dell",
    "00:25:64": "HP",           "3c:d9:2b": "HP",
    "00:50:ba": "D-Link",       "00:1c:f0": "D-Link",
    "00:18:e7": "Netgear",      "2c:30:33": "Netgear",
    "ec:08:6b": "TP-Link",      "50:c7:bf": "TP-Link",
    "c4:e9:84": "TP-Link",      "00:26:b9": "Samsung",
    "8c:77:12": "Samsung",      "00:e0:4c": "Realtek",
    "fc:aa:14": "Amazon Echo",  "b4:75:0e": "Huawei",
    "4c:5e:0c": "Huawei",
}

def _mac_vendor(mac: str) -> str:
    return _OUI.get(mac[:8].lower(), "")


# ══════════════════════════════════════════════════════════════════════════
#  Network info helpers
# ══════════════════════════════════════════════════════════════════════════

def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        pass
    try:
        for _, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    return a.address
    except Exception:
        pass
    return "127.0.0.1"


def _get_gateway(local_ip: str) -> Optional[str]:
    """
    Find the default gateway IP.
    Works on Windows (ipconfig), Linux (ip route), macOS (netstat).
    Falls back to <subnet>.1 which is almost always correct.
    """
    prefix = ".".join(local_ip.split(".")[:3])
    try:
        if _SYS == "windows":
            out = subprocess.check_output(
                ["ipconfig"], text=True, timeout=4,
                creationflags=0x08000000,
            )
            for line in out.splitlines():
                if "Default Gateway" in line or "Passerelle" in line:
                    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                    if m and not m.group(1).startswith("0."):
                        return m.group(1)
        elif _SYS == "linux":
            out = subprocess.check_output(
                ["ip", "route", "show", "default"], text=True, timeout=3
            )
            m = re.search(r"default via (\d{1,3}(?:\.\d{1,3}){3})", out)
            if m:
                return m.group(1)
        elif _SYS == "darwin":
            out = subprocess.check_output(
                ["netstat", "-rn"], text=True, timeout=3
            )
            for line in out.splitlines():
                if line.startswith("default"):
                    m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
                    if m:
                        return m.group(1)
    except Exception:
        pass
    # fallback: .1 is the router on 99% of home networks
    return f"{prefix}.1"


def _get_subnet_prefix(ip: str) -> str:
    return ".".join(ip.split(".")[:3])


def _get_host_list(local_ip: str) -> List[str]:
    try:
        net = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        return [str(h) for h in net.hosts() if str(h) != local_ip]
    except Exception:
        p = _get_subnet_prefix(local_ip)
        return [f"{p}.{i}" for i in range(1, 255) if f"{p}.{i}" != local_ip]


def _connection_type() -> str:
    try:
        for name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET and not a.address.startswith("127."):
                    n = name.lower()
                    if any(x in n for x in ("wlan", "wifi", "wi-fi", "wireless", "wl")):
                        return "Wi-Fi"
                    if any(x in n for x in ("eth", "en", "ether")):
                        return "Ethernet"
    except Exception:
        pass
    return "Unknown"


# ══════════════════════════════════════════════════════════════════════════
#  Scan primitives
# ══════════════════════════════════════════════════════════════════════════

def _get_arp_table() -> Dict[str, str]:
    """Read OS ARP cache → {ip: mac}. No network traffic, instant."""
    table: Dict[str, str] = {}
    try:
        if _SYS == "windows":
            out = subprocess.check_output(
                ["arp", "-a"], text=True, timeout=5,
                creationflags=0x08000000,
            )
            for line in out.splitlines():
                m = re.search(
                    r"(\d{1,3}(?:\.\d{1,3}){3})\s+([\da-f]{2}(?:[:\-][\da-f]{2}){5})",
                    line, re.I,
                )
                if m:
                    mac = m.group(2).replace("-", ":").lower()
                    if "ff:ff:ff:ff:ff:ff" not in mac:
                        table[m.group(1)] = mac
        else:
            for cmd in [["arp", "-n"], ["ip", "neigh", "show"]]:
                try:
                    out = subprocess.check_output(cmd, text=True, timeout=4)
                    for line in out.splitlines():
                        m = re.search(
                            r"(\d{1,3}(?:\.\d{1,3}){3}).*?"
                            r"([\da-f]{2}(?::[\da-f]{2}){5})",
                            line, re.I,
                        )
                        if m:
                            mac = m.group(2).lower()
                            if "ff:ff:ff:ff:ff:ff" not in mac:
                                table[m.group(1)] = mac
                    if table:
                        break
                except Exception:
                    pass
    except Exception:
        pass
    return table


def _tcp_probe(host: str, timeout: float = 0.45) -> Optional[float]:
    """
    Try TCP connect on ordered port list.
    Port 53 (DNS) is attempted first — open on ALL routers.
    Returns latency ms on first success, None if all fail.
    No ICMP needed. Works through Windows Firewall.
    """
    t0 = time.time()
    for port in _PROBE_PORTS:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            if s.connect_ex((host, port)) == 0:
                s.close()
                return round((time.time() - t0) * 1000, 1)
            s.close()
        except Exception:
            pass
    return None


def _ping(host: str, timeout: float = 0.8) -> Optional[float]:
    """ICMP ping — may be blocked by Windows Firewall, used as bonus check."""
    try:
        t0 = time.time()
        if _SYS == "windows":
            r = subprocess.run(
                ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host],
                capture_output=True, text=True, timeout=timeout + 1,
                creationflags=0x08000000,
            )
        elif _SYS == "darwin":
            r = subprocess.run(
                ["ping", "-c", "1", "-W", str(int(timeout * 1000)), host],
                capture_output=True, text=True, timeout=timeout + 1,
            )
        else:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "1", host],
                capture_output=True, text=True, timeout=timeout + 1,
            )
        if r.returncode == 0:
            return round((time.time() - t0) * 1000, 1)
    except Exception:
        pass
    return None


def _is_alive(host: str) -> Optional[float]:
    """TCP probe first (works through firewall), fallback to ping."""
    ms = _tcp_probe(host, timeout=0.45)
    if ms is None:
        ms = _ping(host, timeout=0.7)
    return ms


def _rdns(ip: str, timeout: float = 0.6) -> str:
    result = [""]
    def _go():
        try:
            result[0] = socket.gethostbyaddr(ip)[0]
        except Exception:
            pass
    t = threading.Thread(target=_go, daemon=True)
    t.start(); t.join(timeout=timeout)
    return result[0]


def _make_entry(ip: str, mac: str, latency, hostname: str = "") -> dict:
    return {
        "ip": ip, "mac": mac, "vendor": _mac_vendor(mac),
        "hostname": hostname, "latency_ms": latency, "status": "Online",
    }


# ══════════════════════════════════════════════════════════════════════════
#  NetworkScanThread
# ══════════════════════════════════════════════════════════════════════════

class NetworkScanThread(QThread):
    hostFound    = pyqtSignal(dict)
    scanProgress = pyqtSignal(int, int)
    scanComplete = pyqtSignal(list)

    def __init__(self, local_ip: str, parent=None):
        super().__init__(parent)
        self.local_ip = local_ip
        self._stop    = False

    def stop(self):
        self._stop = True

    def run(self):
        results: List[dict] = []
        seen:    set         = set()
        lock = threading.Lock()
        prefix = _get_subnet_prefix(self.local_ip)

        def emit_host(entry: dict):
            """Thread-safe: add to results and fire signal."""
            with lock:
                ip = entry["ip"]
                if ip in seen:
                    # update existing entry with better info
                    for r in results:
                        if r["ip"] == ip:
                            if entry["latency_ms"] != "ARP":
                                r["latency_ms"] = entry["latency_ms"]
                            if entry.get("hostname"):
                                r["hostname"] = entry["hostname"]
                            if entry.get("mac") and not r["mac"]:
                                r["mac"]    = entry["mac"]
                                r["vendor"] = entry["vendor"]
                    self.hostFound.emit(dict(entry))
                else:
                    seen.add(ip)
                    results.append(dict(entry))
                    self.hostFound.emit(dict(entry))

        # ─── Step 1: Gateway — always the first device found ──────────
        gw = _get_gateway(self.local_ip)
        if gw and gw != self.local_ip and not self._stop:
            # emit gateway immediately (it's always alive)
            arp0 = _get_arp_table()
            mac0 = arp0.get(gw, "")
            emit_host(_make_entry(gw, mac0, "ARP", "Gateway"))
            # probe in background to get real latency
            def _gw_latency():
                ms = _is_alive(gw)
                if ms:
                    hn = _rdns(gw)
                    emit_host(_make_entry(gw, arp0.get(gw, ""), ms,
                                         hn or "Gateway"))
            threading.Thread(target=_gw_latency, daemon=True).start()

        # ─── Step 2: Read ARP table — other cached devices ────────────
        arp = _get_arp_table()
        for ip, mac in arp.items():
            if self._stop:
                break
            if ip == self.local_ip:
                continue
            if not ip.startswith(prefix + "."):
                continue
            emit_host(_make_entry(ip, mac, "ARP"))

        # ─── Step 3: Full concurrent TCP probe on all 254 hosts ───────
        hosts = _get_host_list(self.local_ip)
        total = len(hosts)
        done  = [0]

        def probe(host: str):
            if self._stop:
                return
            ms = _is_alive(host)
            with lock:
                done[0] += 1
            self.scanProgress.emit(done[0], total)
            if ms is None:
                return
            mac = arp.get(host, "")
            hn  = _rdns(host)
            emit_host(_make_entry(host, mac, ms, hn))

        threads = [threading.Thread(target=probe, args=(h,), daemon=True)
                   for h in hosts]
        for th in threads:
            th.start()
        for th in threads:
            if self._stop:
                break
            th.join(timeout=60)

        # ─── Step 4: Second ARP read — fill in missing MACs ───────────
        arp2 = _get_arp_table()
        with lock:
            for r in results:
                if not r["mac"] and r["ip"] in arp2:
                    r["mac"]    = arp2[r["ip"]]
                    r["vendor"] = _mac_vendor(r["mac"])

        results.sort(key=lambda e: (
            0 if e.get("hostname") == "Gateway" else 1,
            int(e["ip"].split(".")[-1]),
        ))
        self.scanComplete.emit(results)


# ══════════════════════════════════════════════════════════════════════════
#  LatencyThread
# ══════════════════════════════════════════════════════════════════════════

class LatencyThread(QThread):
    result  = pyqtSignal(str, float)
    TARGETS = ["1.1.1.1", "8.8.8.8"]

    def run(self):
        for host in self.TARGETS:
            ms = _ping(host, timeout=2.0)
            if ms is None:
                # fallback: TCP-80 (HTTP)
                try:
                    t0 = time.time()
                    s  = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2.0)
                    if s.connect_ex((host, 80)) == 0:
                        ms = round((time.time() - t0) * 1000, 1)
                    s.close()
                except Exception:
                    pass
            self.result.emit(host, ms if ms is not None else -1.0)


# ══════════════════════════════════════════════════════════════════════════
#  NetworkManager — public API consumed by main_gui.py
# ══════════════════════════════════════════════════════════════════════════

class NetworkManager(QObject):
    infoReady    = pyqtSignal(dict)
    hostFound    = pyqtSignal(dict)
    scanProgress = pyqtSignal(int, int)
    scanFinished = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._local_ip  = _get_local_ip()
        self._subnet    = _get_subnet_prefix(self._local_ip)
        self._conn_type = _connection_type()
        self._latencies: Dict[str, float] = {}
        self._scan_thread: Optional[NetworkScanThread] = None
        self._lat_thread:  Optional[LatencyThread]     = None

    def get_basic_info(self) -> dict:
        return {
            "local_ip":        self._local_ip,
            "subnet":          self._subnet,
            "connection_type": self._conn_type,
            "latencies":       dict(self._latencies),
        }

    def probe_latency(self):
        if self._lat_thread and self._lat_thread.isRunning():
            return
        self._lat_thread = LatencyThread(self)
        self._lat_thread.result.connect(self._on_latency)
        self._lat_thread.start()

    def _on_latency(self, host: str, ms: float):
        self._latencies[host] = ms
        self.infoReady.emit(self.get_basic_info())

    def start_scan(self):
        if self._scan_thread and self._scan_thread.isRunning():
            return
        self._scan_thread = NetworkScanThread(self._local_ip, self)
        self._scan_thread.hostFound.connect(self.hostFound)
        self._scan_thread.scanProgress.connect(self.scanProgress)
        self._scan_thread.scanComplete.connect(self.scanFinished)
        self._scan_thread.start()

    def stop_scan(self):
        if self._scan_thread:
            self._scan_thread.stop()
