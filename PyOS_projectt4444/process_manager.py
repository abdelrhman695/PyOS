"""
Process Manager Module
Handles simulated process creation, scheduling (Round Robin),
and optionally exposes real system processes via psutil.
"""

import time
import threading
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict
import psutil


class ProcessState(Enum):
    RUNNING = "Running"
    READY = "Ready"
    WAITING = "Waiting"
    TERMINATED = "Terminated"


@dataclass
class SimProcess:
    pid: int
    name: str
    state: ProcessState
    priority: int
    cpu_usage: float = 0.0
    memory_mb: float = 0.0
    created_at: float = field(default_factory=time.time)
    burst_time: int = 0
    quantum_remaining: int = 0

    def to_dict(self) -> dict:
        return {
            "pid": self.pid,
            "name": self.name,
            "state": self.state.value,
            "priority": self.priority,
            "cpu_usage": round(self.cpu_usage, 1),
            "memory_mb": round(self.memory_mb, 1),
            "created_at": self.created_at,
        }


class RoundRobinScheduler:
    QUANTUM = 100

    def __init__(self):
        self.queue: List[SimProcess] = []
        self.current_index = 0

    def add(self, proc: SimProcess):
        proc.quantum_remaining = self.QUANTUM
        self.queue.append(proc)

    def remove(self, pid: int):
        self.queue = [p for p in self.queue if p.pid != pid]
        if self.current_index >= len(self.queue):
            self.current_index = 0

    def tick(self):
        active = [p for p in self.queue if p.state != ProcessState.TERMINATED]
        if not active:
            return

        for proc in active:
            if proc.state == ProcessState.RUNNING:
                proc.quantum_remaining -= 10
                if proc.quantum_remaining <= 0:
                    proc.state = ProcessState.READY
                    proc.quantum_remaining = self.QUANTUM

        ready = [p for p in active if p.state == ProcessState.READY]
        if ready and not any(p.state == ProcessState.RUNNING for p in active):
            chosen = ready[self.current_index % len(ready)]
            chosen.state = ProcessState.RUNNING
            chosen.quantum_remaining = self.QUANTUM
            self.current_index = (self.current_index + 1) % len(ready)


class ProcessManager:
    _next_pid = 1000

    def __init__(self):
        self._lock = threading.Lock()
        self._processes: Dict[int, SimProcess] = {}
        self._scheduler = RoundRobinScheduler()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks = []

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def create_process(self, name: str, priority: int = 5,
                       burst_time: int = 500) -> SimProcess:
        with self._lock:
            pid = ProcessManager._next_pid
            ProcessManager._next_pid += 1
            proc = SimProcess(
                pid=pid,
                name=name,
                state=ProcessState.READY,
                priority=priority,
                memory_mb=random.uniform(10, 256),
                burst_time=burst_time,
                quantum_remaining=RoundRobinScheduler.QUANTUM,
            )
            self._processes[pid] = proc
            self._scheduler.add(proc)
            self._notify()
            return proc

    def terminate_process(self, pid: int):
        with self._lock:
            proc = self._processes.get(pid)
            if proc:
                proc.state = ProcessState.TERMINATED
                self._scheduler.remove(pid)
                self._notify()

    def get_all(self) -> List[dict]:
        with self._lock:
            return [p.to_dict() for p in self._processes.values()
                    if p.state != ProcessState.TERMINATED]

    def get_real_processes(self, limit: int = 30) -> List[dict]:
        result = []
        for proc in psutil.process_iter(
                ['pid', 'name', 'status', 'cpu_percent', 'memory_info']):
            try:
                info = proc.info
                mem = info['memory_info']
                result.append({
                    "pid": info['pid'],
                    "name": info['name'] or "(unknown)",
                    "state": info['status'],
                    "cpu_usage": round(info['cpu_percent'] or 0.0, 1),
                    "memory_mb": round((mem.rss if mem else 0) / 1_048_576, 1),
                    "priority": 5,
                    "created_at": 0,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            if len(result) >= limit:
                break
        return result

    def add_callback(self, cb):
        self._callbacks.append(cb)

    def _notify(self):
        for cb in self._callbacks:
            try:
                cb()
            except Exception:
                pass

    def _loop(self):
        while self._running:
            with self._lock:
                self._scheduler.tick()
                for proc in self._processes.values():
                    if proc.state == ProcessState.RUNNING:
                        proc.cpu_usage = random.uniform(5, 40)
                    elif proc.state == ProcessState.READY:
                        proc.cpu_usage = random.uniform(0, 5)
                    else:
                        proc.cpu_usage = 0.0
                    proc.memory_mb = max(
                        1.0,
                        proc.memory_mb + random.uniform(-2, 2)
                    )
            time.sleep(0.5)
