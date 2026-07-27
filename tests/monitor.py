"""
Unit tests for syswatch.monitor.

These use an injected fake sampler so results are deterministic —
we never assert against the real machine's actual CPU/memory load.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from syswatch.monitor import ResourceMonitor, Thresholds, Snapshot


def make_snapshot(cpu=10.0, mem=10.0, disk=10.0) -> Snapshot:
    return Snapshot(timestamp=0.0, cpu_percent=cpu, memory_percent=mem, disk_percent=disk)


class TestResourceMonitor(unittest.TestCase):
    def test_no_alerts_when_under_threshold(self):
        monitor = ResourceMonitor(thresholds=Thresholds(cpu=90, memory=90, disk=90))
        snap = make_snapshot(cpu=50, mem=50, disk=50)
        self.assertEqual(monitor.check(snap), [])

    def test_cpu_alert_triggers_at_threshold(self):
        monitor = ResourceMonitor(thresholds=Thresholds(cpu=80, memory=90, disk=90))
        snap = make_snapshot(cpu=80.0, mem=10, disk=10)
        alerts = monitor.check(snap)
        self.assertEqual(len(alerts), 1)
        self.assertIn("CPU usage", alerts[0])

    def test_multiple_alerts_can_fire_together(self):
        monitor = ResourceMonitor(thresholds=Thresholds(cpu=50, memory=50, disk=50))
        snap = make_snapshot(cpu=95, mem=95, disk=95)
        alerts = monitor.check(snap)
        self.assertEqual(len(alerts), 3)

    def test_sample_uses_injected_sampler_not_real_machine(self):
        fake = make_snapshot(cpu=42, mem=43, disk=44)
        monitor = ResourceMonitor(sampler=lambda: fake)
        result = monitor.sample()
        self.assertEqual(result, fake)

    def test_as_dict_serializes_snapshot(self):
        snap = make_snapshot(cpu=1, mem=2, disk=3)
        d = snap.as_dict()
        self.assertEqual(d["cpu_percent"], 1)
        self.assertEqual(d["memory_percent"], 2)
        self.assertEqual(d["disk_percent"], 3)


class TestTopProcesses(unittest.TestCase):
    def test_rejects_invalid_sort_by(self):
        monitor = ResourceMonitor()
        with self.assertRaises(ValueError):
            monitor.top_processes(sort_by="bogus")

    def test_returns_at_most_requested_count(self):
        monitor = ResourceMonitor()
        # Real processes on this machine -- we only assert on shape/size,
        # never on which specific process "wins", since that's nondeterministic.
        top = monitor.top_processes(count=3, sort_by="cpu")
        self.assertLessEqual(len(top), 3)
        for entry in top:
            self.assertIn("pid", entry)
            self.assertIn("name", entry)
            self.assertIn("cpu_percent", entry)
            self.assertIn("memory_percent", entry)

    def test_sorted_descending_by_requested_field(self):
        monitor = ResourceMonitor()
        top = monitor.top_processes(count=10, sort_by="memory")
        values = [p["memory_percent"] for p in top]
        self.assertEqual(values, sorted(values, reverse=True))


if __name__ == "__main__":
    unittest.main()