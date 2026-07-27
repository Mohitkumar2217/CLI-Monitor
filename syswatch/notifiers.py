"""
notifiers.py
Alert delivery backends: log, Slack, PagerDuty.
 
Design choices:
  - Notifier is a small interface (`notify(message) -> bool`) so adding a
    new backend (email, Opsgenie, webhook-of-your-own) means writing one
    class, not touching the monitor loop.
  - CompositeNotifier fans an alert out to every enabled backend and
    isolates failures: if Slack's webhook is down, PagerDuty still fires.
    A single flaky integration should never silently swallow all alerting.
  - Network calls use short timeouts so a hung endpoint can't stall the
    whole monitoring loop.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import requests 

logger = logging.getLogger("syswatch")

REQUEST_TIMEOUT_SECONDS = 5

class Notifier(ABC):
    @abstractmethod
    def notify(self, message: str) -> bool:
        """Send `message`. Return True on success, False on failure."""
        raise NotImplementedError

class LogNotifier(Notifier):
    """ALways-available fallback: just logs the alert."""

    def notify(self, message: str) -> bool:
        logger.warning("ALERT: %s", message)
        return True

class SlackNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, message: str) -> bool:
        try:
            resp = requests.post(
                self.webhook_url,
                json={"text": f":rotating_light: syswatch alert: {message}"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("Slack notification failed: %s", e)
            return False

class PagerDutyNotifier(Notifier):
    EVENTS_API_URL = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, routing_key: str, api_url: Optional[str] = None):
        self.routing_key = routing_key
        self.api_url = api_url or self.EVENTS_API_URL

    def notify(self, message: str) -> bool:
        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": message,
                "source": "syswatch",
                "severity": "warning",
            },
        }

        try:
            resp = requests.post(self.api_url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("PagerDuty notification failed: %s", e)
            return False
        
class CompositeNotifier(Notifier):
    """Fans an alert out to multiple notifiers; one failure doesn't stop the rest."""

    def __init__(self, notifiers: list[Notifier]):
        self.notifiers = notifiers

    def notify(self, message: str) -> bool:
        results = []
        for n in self.notifiers:
            try:
                results.append(n.notify(message))
            except Exception as e: # a notifier bug should never crahs the loop
                logger.error("Notifier %s raised an exception: %s", type(n).__name__, e)
                results.append(False)
        return any(results)

def build_notifier_from_config(notifiers_config) -> CompositeNotifier:
    """Construct the composite notifier from a NotifiersConfig object."""
    active: list[Notifier] = []
    if notifiers_config.log.enabled:
        active.append(LogNotifier())
    if notifiers_config.slack.enabled:
        active.append(SlackNotifier(notifiers_config.slack.webhook_url))
    if notifiers_config.pagerduty.enabled:
        active.append(PagerDutyNotifier(notifiers_config.pagerduty.routing_key))

    return CompositeNotifier(active)
