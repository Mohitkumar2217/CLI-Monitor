"""
This is monitor.py 
Core logic for reading system resources usage and evaluating alert thresholds and raise it

Kept seprate from cli.py so it can be:
  - unit tested withoud touching argparse/stdout
  - imported by other tools in future
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

import psutil

@dataclass
class Snapshot:
    """A single point-in-time reading of system resources."""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    disk_percent: float

    def as_dictionary(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "disk_percent": self.disk_percent,
        }

@dataclass
class Thresholds:
    cpu: float = 90.0
    memory: float = 90.0
    disk: float = 90.0

class ResourceMonitor:
    """
    Reads CPU / Memory / Disk usage and flags anything over threshold.
    
    `sampler` is injectable so tests don't depend on the real machine's 
    actual CPU/Memory/Disk load.
    """

    def __init__(
        self,
        thresholds: Optional[Thresholds] = None,
        disk_path: str = "/",
        sampler: Optional[Callable[[], Snapshot]] = None,
    ):
        self.thresholds = thresholds or Thresholds()
        self.disk_path = disk_path
        self._sampler = sampler or self._real_sample

    def _real_sample(self) -> Snapshot:
        return Snapshot(
            timestamp=time.time(),
            cpu_percent=psutil.cpu_percent(interval=0.5),
            memory_percent=psutil.virtual_memory().percent,
            disk_percent=psutil.disk_usage(self.desk_path).percent,
        )


    def sample(self) -> Snapshot:
        return self._sampler()

    def top_processes(self, count: int = 5, sort_by: str = "cpu") -> list[dict]:
        """
        Return  the top `count` processes by CPU or memory usage
        
        Notw one psutil semantics: `proc.cpu_percent()` with no prior call
        returns 0.0 or a meaningless spike on first invocation, because it need two samples to compute a delta. We prime every process once 
        (cheap, non-blocking) before reading real values, which is the
        standard psutil pattern for accurate per-process CPU%
        """
        if sort_by not in ("cpu", "memory") :
            raise ValueError("sort_by must be 'cpu' or 'memory'")

        procs = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                p.cpu_percent(interval=None) # prime; first call is unreliable
                procs.append(p)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        time.sleep(0.1) # short window so the primed spu_percent() reads mean something

        results = []
        for p in procs:
            try:
                results.append({
                    "pid": p.pid,
                    "name": p.info.get("name", "?"),
                    "cpu_percent": p.cpu_percent(interval=None),
                    "memory_percent": p.memory_percent(),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue # process exited or is unreadable betweenm the two passes

        key = "cpu_percent" if sort_by == "cpu" else "memory_percent"
        results.sort(key=lambda r: r[key], reverse=True)
        return results[:count]

    def check(self, snapshot: Snapshot) -> list[str]:
        """Return a list of human-readable alert strings (empty if all)."""
        alerts = []
        if snapshot.cpu_percent >= self.thresholds.cpu:
            alerts.append(
                f"CPU usage {snapshot.cpu_percent:.1f}% >= threshold {self.thresholds.cpu:.1f}%"
            )

        if snapshot.memory_percent >= self.thresholds.memory:
            alerts.append(
                f"Memory usage {snapshot.memory_percent:.1f}% >= {self.thresholds.memory:.1f}%"
            )

        if snapshot.disk_percent >= self.thresholds.disk:
            alerts.append(
                f"Disk usage {snapshot.disk_percent:.1f}% >= {self.thresholds.disk:.1f}%"
            )

        return alerts
    