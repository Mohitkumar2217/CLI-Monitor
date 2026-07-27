import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from syswatch.notifiers import (
    LogNotifier,
    SlackNotifier,
    PagerDutyNotifier,
    CompositeNotifier,
)


class TestLogNotifier(unittest.TestCase):
    def test_always_succeeds(self):
        self.assertTrue(LogNotifier().notify("test alert"))


class TestSlackNotifier(unittest.TestCase):
    @patch("syswatch.notifiers.requests.post")
    def test_sends_correct_payload(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/x")
        result = notifier.notify("CPU high")

        self.assertTrue(result)
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://hooks.slack.com/x")
        self.assertIn("CPU high", kwargs["json"]["text"])
        self.assertEqual(kwargs["timeout"], 5)

    @patch("syswatch.notifiers.requests.post")
    def test_network_failure_returns_false_not_exception(self, mock_post):
        import requests
        mock_post.side_effect = requests.ConnectionError("boom")
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/x")
        result = notifier.notify("CPU high")
        self.assertFalse(result)


class TestPagerDutyNotifier(unittest.TestCase):
    @patch("syswatch.notifiers.requests.post")
    def test_sends_correct_event_payload(self, mock_post):
        mock_post.return_value = MagicMock(status_code=202, raise_for_status=lambda: None)
        notifier = PagerDutyNotifier(routing_key="rk_123")
        result = notifier.notify("Disk full")

        self.assertTrue(result)
        args, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["routing_key"], "rk_123")
        self.assertEqual(payload["event_action"], "trigger")
        self.assertEqual(payload["payload"]["summary"], "Disk full")


class TestCompositeNotifier(unittest.TestCase):
    def test_calls_all_notifiers(self):
        n1, n2 = MagicMock(spec=LogNotifier), MagicMock(spec=LogNotifier)
        n1.notify.return_value = True
        n2.notify.return_value = True
        composite = CompositeNotifier([n1, n2])

        composite.notify("alert")

        n1.notify.assert_called_once_with("alert")
        n2.notify.assert_called_once_with("alert")

    def test_one_failure_does_not_block_others(self):
        failing = MagicMock(spec=LogNotifier)
        failing.notify.side_effect = Exception("this backend is broken")
        working = MagicMock(spec=LogNotifier)
        working.notify.return_value = True

        composite = CompositeNotifier([failing, working])
        result = composite.notify("alert")

        # working notifier still got called despite failing one raising
        working.notify.assert_called_once_with("alert")
        self.assertTrue(result)  # overall success because at least one succeeded

    def test_all_failing_returns_false(self):
        n1 = MagicMock(spec=LogNotifier)
        n1.notify.return_value = False
        n2 = MagicMock(spec=LogNotifier)
        n2.notify.return_value = False

        composite = CompositeNotifier([n1, n2])
        self.assertFalse(composite.notify("alert"))


if __name__ == "__main__":
    unittest.main()