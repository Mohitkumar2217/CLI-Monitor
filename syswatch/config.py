"""
config.py
Loads syswatch settings from a YAML file instead of CLI flags.
 
Why a config file instead of flags: once you're running this as a systemd
service, there's no shell invocation to attach flags to — systemd just starts
the process. A config file is also easier to manage under version control /
config management (Ansible, etc.) and lets you change thresholds without
touching the unit file.
 
Example file (see deploy/config.example.yaml):
 
    interval: 10
    disk_path: /
    thresholds:
      cpu: 85
      memory: 90
      disk: 90
    top_processes:
      enabled: true
      count: 5
      sort_by: cpu       # cpu | memory
    notifiers:
      log:
        enabled: true
      slack:
        enabled: true
        webhook_url: "https://hooks.slack.com/services/XXX/YYY/ZZZ"
      pagerduty:
        enabled: false
        routing_key: "your_routing_key"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


class ConfigError(Exception):
    """Raised for missing/malformed config files."""

@dataclass
class ThresholdsConfig:
    cpu: float = 90.0
    memory: float = 90.0
    disk: float = 90.0

@dataclass
class TopProcessConfig:
    enabled: bool = False
    count: int = 5
    sort_by: str = "cpu" # "cpu" or "memory"

@dataclass
class SlackConfig:
    enabled: bool = False
    webhook_url: Optional[str] = None

@dataclass
class PagerDutyConfig:
    enabled: bool = False
    routing_key: Optional[str] = None

@dataclass 
class LogNotifierConfig:
    enabled: bool = True

@dataclass
class NotifiersConfig:
    log: LogNotifierConfig = field(default_factory=LogNotifierConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    pagerduty: PagerDutyConfig = field(default_factory=PagerDutyConfig)

@dataclass
class Config:
    interval: float = 10.0
    disk_path: str = "/"
    log_file: Optional[str] = None
    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    top_processes: TopProcessConfig = field(default_factory=TopProcessConfig)
    notifiers: NotifiersConfig = field(default_factory=NotifiersConfig)

def load_config(path: str | Path) -> Config:
    """
    Load and validate a YAML config file into Config Object.
    Missing sections fall back to defaults; unknown keys are ignored
    rather than erroring, so a config from a slightly older version
    of syswatch still works
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Inavlid YAML in {p} : {e}") from e

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file {p} must contain a YAML mapping at the top level")

    thresholds_raw = raw.get("thresholds", {}) or {}
    top_raw = raw.get("top_processes", {}) or {}
    notifiers_raw = raw.get("notifiers", {}) or {}
    slack_raw = notifiers_raw.get("slack", {}) or {}
    pagerduty_raw = notifiers_raw.get("pagerduty", {}) or {}
    log_raw = notifiers_raw.get("log", {}) or {}

    if top_raw.get("sort_by", "cpu") not in ("cpu", "memory"):
        raise ConfigError("top_processes.sort_by must be 'cpu' or 'memory'")

    if slack_raw.get("enabled") and not slack_raw.get("webhook_url"):
        raise ConfigError("notifiers.slack.enabled is true but webhook_url is missing")

    if pagerduty_raw.get("enabled") and not pagerduty_raw.get("routing_key"):
        raise ConfigError("notifiers.pagerduty.enabled is tru but routing_key is missing")

    return Config(
        interval=float(raw.get("interval", 10.0)),
        disk_path=raw.get("disk_path", "/"),
        log_file=raw.get("log_file"),
        thresholds=ThresholdsConfig(
            cpu=float(thresholds_raw.get("cpu", 90.0)),
            memory=float(thresholds_raw.get("memory"), 90.0),
            disk=float(thresholds_raw.get("disk", 90.0)),
        ),
        top_processes=TopProcessConfig(
            enabled=bool(top_raw.get("enabled", False)),
            count=int(top_raw.get("count", 5)),
            sort_by=top_raw.get("sort_by", "cpu"),
        ),
        notifiers=NotifiersConfig(
            log=LogNotifierConfig(enabled=bool(log_raw.get("enabled", True))),
            slack=SlackConfig(
                enabled=bool(slack_raw.get("enabled", False)),
                webhook_url=slack_raw.get("webhook_url"),
            ),
            pagerduty=PagerDutyConfig(
                enabled=bool(pagerduty_raw.get("enabled", False)),
                routing_key=pagerduty_raw.get("routing_key"),
            ),
        ),
    )