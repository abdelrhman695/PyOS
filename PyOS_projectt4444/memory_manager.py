"""
Memory Manager Module
Simulates fixed-partition memory allocation with a visual block map.
"""

import threading
from dataclasses import dataclass, field
from typing import List, Optional, Dict


TOTAL_MEMORY_MB = 1024
BLOCK_SIZE_MB = 32


@dataclass
class MemoryBlock:
    index: int
    size_mb: int = BLOCK_SIZE_MB
    allocated: bool = False
    pid: Optional[int] = None
    process_name: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "size_mb": self.size_mb,
            "allocated": self.allocated,
            "pid": self.pid,
            "process_name": self.process_name,
        }


class MemoryManager:
    """
    Fixed-partition memory manager.
    Each process is allocated one or more contiguous blocks.
    """

    def __init__(self):
        num_blocks = TOTAL_MEMORY_MB // BLOCK_SIZE_MB
        self._blocks: List[MemoryBlock] = [
            MemoryBlock(index=i) for i in range(num_blocks)
        ]
        self._lock = threading.Lock()
        self._alloc_map: Dict[int, List[int]] = {}

    def allocate(self, pid: int, name: str, size_mb: float) -> bool:
        needed = max(1, int(size_mb / BLOCK_SIZE_MB))
        with self._lock:
            free_indices = [b.index for b in self._blocks if not b.allocated]
            if len(free_indices) < needed:
                return False
            chosen = free_indices[:needed]
            for idx in chosen:
                self._blocks[idx].allocated = True
                self._blocks[idx].pid = pid
                self._blocks[idx].process_name = name
            self._alloc_map[pid] = chosen
            return True

    def deallocate(self, pid: int):
        with self._lock:
            for idx in self._alloc_map.pop(pid, []):
                blk = self._blocks[idx]
                blk.allocated = False
                blk.pid = None
                blk.process_name = ""

    def get_map(self) -> List[dict]:
        with self._lock:
            return [b.to_dict() for b in self._blocks]

    def stats(self) -> dict:
        with self._lock:
            used = sum(1 for b in self._blocks if b.allocated)
            total = len(self._blocks)
            free = total - used
            return {
                "total_mb": TOTAL_MEMORY_MB,
                "used_mb": used * BLOCK_SIZE_MB,
                "free_mb": free * BLOCK_SIZE_MB,
                "used_pct": round(100 * used / total, 1),
                "blocks_total": total,
                "blocks_used": used,
                "blocks_free": free,
            }
