# syswatch

A small, dependency-light system resource monitor: watches CPU, memory, and
disk usage, alerts to log/Slack/PagerDuty when thresholds are crossed, reports
the top resource-consuming processes during an alert, and runs unattended as
a systemd service.

## Architecture

- **`monitor.py`** — core logic (sampling, threshold checks, per-process
  tracking). No dependency on argparse or stdout, so it's fully unit
  testable. The resource sampler is injectable, which is what makes tests
  deterministic instead of depending on the real machine's live load.
- **`config.py`** — loads settings from a YAML file instead of CLI flags.
  A config file is what lets this run as a systemd service (no shell
  invocation to attach flags to) and be managed under version control.
- **`notifiers.py`** — pluggable alert backends (log / Slack / PagerDuty).
  `CompositeNotifier` fans an alert out to every enabled backend and
  isolates failures — if Slack's webhook is down, PagerDuty still fires,
  and a single flaky integration can't silently swallow all alerting.
- **`cli.py`** — thin entrypoint: loads config, wires up the monitor and
  notifiers, runs the loop.

```
syswatch/
├── syswatch/
│   ├── monitor.py     # sampling + threshold + per-process logic
│   ├── config.py      # YAML config loading & validation
│   ├── notifiers.py   # log / Slack / PagerDuty
│   └── cli.py         # entrypoint
├── tests/             # 20 unit tests, no real network calls
├── deploy/
│   ├── syswatch.service       # systemd unit file
│   └── config.example.yaml    # starting point for /etc/syswatch/config.yaml
└── requirements.txt
```

## Install

```bash
pip install -r requirements.txt
```

## Usage (ad-hoc / cron)

```bash
python -m syswatch.cli --config ./deploy/config.example.yaml --once
```

## Configuration

Copy `deploy/config.example.yaml`, then edit thresholds and notifier settings:

```yaml
thresholds:
  cpu: 85
  memory: 90
  disk: 90
top_processes:
  enabled: true      # log top CPU/memory processes when an alert fires
  count: 5
  sort_by: cpu
notifiers:
  slack:
    enabled: true
    webhook_url: "https://hooks.slack.com/services/..."
  pagerduty:
    enabled: true
    routing_key: "your_routing_key"
```

Unknown keys are ignored and missing sections fall back to defaults, so
older config files keep working after upgrades. Enabling a notifier without
its required field (e.g. `slack.enabled: true` with no `webhook_url`) fails
fast at startup with a clear error instead of failing silently later.

## Deploying as a systemd service

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin syswatch
sudo mkdir -p /opt/syswatch /etc/syswatch /var/log/syswatch
sudo chown syswatch:syswatch /var/log/syswatch

# copy the project into /opt/syswatch, then:
sudo cp deploy/config.example.yaml /etc/syswatch/config.yaml
sudo cp deploy/syswatch.service /etc/systemd/system/syswatch.service

sudo systemctl daemon-reload
sudo systemctl enable --now syswatch
sudo systemctl status syswatch
journalctl -u syswatch -f
```

The unit file runs as an unprivileged `syswatch` user with `ProtectSystem=strict`
and `ProtectHome=true` — it only needs read access to `/proc` for metrics,
outbound HTTPS for Slack/PagerDuty, and write access to its own log directory.

## Tests

```bash
python -m unittest discover -s tests -v
```

20 tests covering threshold logic, config parsing/validation, per-process
sorting, and notifier fan-out/failure-isolation. Slack/PagerDuty tests mock
`requests.post` — no real network calls are made in the test suite.

## Possible future extensions

- Email notifier
- Per-process alerting (not just system totals) with an allow/deny list
- Prometheus metrics endpoint instead of / in addition to push alerts