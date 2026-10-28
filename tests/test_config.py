"""Settings from the environment, and that every alert has a runbook."""

import ipaddress
from datetime import timedelta
from pathlib import Path

from authwatch import config
from authwatch.alerts import RUNBOOKS
from authwatch.ports import Allowed

ROOT = Path(__file__).parent.parent


def test_defaults():
    cfg = config.load({})
    assert cfg.log_file == "/var/log/auth.log"
    assert cfg.allowed_ports == [Allowed(22)]
    assert cfg.ignore_loopback
    assert not cfg.from_start
    assert cfg.bursts.per_source == 20
    assert cfg.bursts.total_window == timedelta(minutes=10)


def test_overrides():
    cfg = config.load(
        {
            "AUTHWATCH_ALLOWED_PORTS": "22, 80,443 ,10.0.0.5:8080",
            "AUTHWATCH_KNOWN_NETWORKS": "192.0.2.0/24,2001:db8::/32",
            "AUTHWATCH_BURST_PER_SOURCE": "7",
            "AUTHWATCH_IGNORE_LOOPBACK": "false",
            "AUTHWATCH_LOG_FILE": "-",
        }
    )
    assert cfg.allowed_ports == [Allowed(22), Allowed(80), Allowed(443), Allowed(8080, "10.0.0.5")]
    assert cfg.known_networks == [
        ipaddress.ip_network("192.0.2.0/24"),
        ipaddress.ip_network("2001:db8::/32"),
    ]
    assert cfg.bursts.per_source == 7
    assert not cfg.ignore_loopback
    assert cfg.log_file == "-"


def test_every_alert_has_a_runbook_file():
    for name, slug in RUNBOOKS.items():
        assert (ROOT / "docs" / "runbooks" / f"{slug}.md").is_file(), name
