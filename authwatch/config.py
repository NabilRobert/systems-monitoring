"""Settings, from environment variables (see .env.example)."""

import ipaddress
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from authwatch.detect import BurstRules, Network
from authwatch.ports import Allowed

DEFAULT_RUNBOOKS = "https://github.com/NabilRobert/systems-monitoring/blob/main/docs/runbooks"


@dataclass(frozen=True, slots=True)
class Config:
    alertmanager_url: str
    log_file: str  # a path, or "-" for standard input
    host_label: str
    runbook_base: str
    known_networks: list[Network]
    bursts: BurstRules
    proc_net: Path
    allowed_ports: list[Allowed]
    port_interval: timedelta
    ignore_loopback: bool
    poll_interval: float
    from_start: bool
    alive_file: Path | None


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


def load(env: Mapping[str, str] = os.environ) -> Config:
    def get(name: str, default: str) -> str:
        return env.get(f"AUTHWATCH_{name}", default)

    alive = get("ALIVE_FILE", "")
    return Config(
        alertmanager_url=get("ALERTMANAGER_URL", "http://alertmanager:9093"),
        log_file=get("LOG_FILE", "/var/log/auth.log"),
        host_label=get("HOST_LABEL", "server"),
        runbook_base=get("RUNBOOK_BASE", DEFAULT_RUNBOOKS),
        known_networks=[
            ipaddress.ip_network(net, strict=False) for net in _split(get("KNOWN_NETWORKS", ""))
        ],
        bursts=BurstRules(
            per_source=int(get("BURST_PER_SOURCE", "20")),
            per_source_window=timedelta(seconds=int(get("BURST_WINDOW_SECONDS", "60"))),
            total=int(get("FLOOD_TOTAL", "200")),
            total_window=timedelta(seconds=int(get("FLOOD_WINDOW_SECONDS", "600"))),
        ),
        proc_net=Path(get("PROC_NET", "/proc/net")),
        allowed_ports=[Allowed.parse(entry) for entry in _split(get("ALLOWED_PORTS", "22"))],
        port_interval=timedelta(seconds=int(get("PORT_INTERVAL_SECONDS", "30"))),
        ignore_loopback=_bool(get("IGNORE_LOOPBACK", "true")),
        poll_interval=float(get("POLL_INTERVAL_SECONDS", "1")),
        from_start=_bool(get("FROM_START", "false")),
        alive_file=Path(alive) if alive else None,
    )
