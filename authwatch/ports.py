"""New listening TCP ports, from the kernel's socket tables.

`/proc/net/tcp` and `/proc/net/tcp6` list every TCP socket in the network
namespace. Run with the host's namespace, they show the host's listeners,
with no tools in the image and no privileges.
"""

import ipaddress
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from authwatch.alerts import PAGE, Alert

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

_LISTEN = "0A"


@dataclass(frozen=True, slots=True, order=True)
class Listener:
    address: str
    port: int

    @property
    def ip(self) -> IPAddress:
        return ipaddress.ip_address(self.address)

    @property
    def is_loopback(self) -> bool:
        ip = self.ip
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            return ip.ipv4_mapped.is_loopback
        return ip.is_loopback

    def __str__(self) -> str:
        host = f"[{self.address}]" if ":" in self.address else self.address
        return f"{host}:{self.port}"


def _decode_address(hex_addr: str) -> str:
    # The kernel prints each 32-bit word in host byte order (little-endian
    # on x86 and arm64), so each 4-byte group is reversed.
    raw = bytes.fromhex(hex_addr)
    swapped = b"".join(raw[i : i + 4][::-1] for i in range(0, len(raw), 4))
    return str(ipaddress.ip_address(swapped))


def parse_proc_net_tcp(text: str) -> set[Listener]:
    """The listening sockets in the text of /proc/net/tcp or tcp6."""
    listeners: set[Listener] = set()
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[3] != _LISTEN:
            continue
        hex_addr, hex_port = fields[1].split(":")
        listeners.add(Listener(_decode_address(hex_addr), int(hex_port, 16)))
    return listeners


def read_listeners(proc_net: Path) -> set[Listener]:
    listeners: set[Listener] = set()
    for name in ("tcp", "tcp6"):
        path = proc_net / name
        if path.exists():
            listeners |= parse_proc_net_tcp(path.read_text())
    return listeners


@dataclass(frozen=True, slots=True)
class Allowed:
    """`22` allows a port on any address; `10.0.0.5:8080` or `[::1]:9000` one address."""

    port: int
    address: str | None = None

    @classmethod
    def parse(cls, entry: str) -> Allowed:
        entry = entry.strip()
        if entry.isdigit():
            return cls(int(entry))
        host, _, port = entry.rpartition(":")
        address = str(ipaddress.ip_address(host.strip("[]")))
        return cls(int(port), address)

    def matches(self, listener: Listener) -> bool:
        return listener.port == self.port and (
            self.address is None or self.address == listener.address
        )


class PortWatcher:
    """Alerts on each listener outside the allow-list, while it listens.

    The alert is re-sent on every check with an end time a few checks
    ahead, so it stays firing while the port is open and resolves by
    itself after the port closes.
    """

    def __init__(self, allowed: list[Allowed], interval: timedelta, ignore_loopback: bool = True):
        self._allowed = allowed
        self._interval = interval
        self._ignore_loopback = ignore_loopback
        self._first_seen: dict[Listener, datetime] = {}

    def unexpected(self, listeners: set[Listener]) -> list[Listener]:
        return sorted(
            listener
            for listener in listeners
            if not (self._ignore_loopback and listener.is_loopback)
            and not any(rule.matches(listener) for rule in self._allowed)
        )

    def check(self, listeners: set[Listener], now: datetime) -> list[Alert]:
        found = self.unexpected(listeners)
        self._first_seen = {listener: self._first_seen.get(listener, now) for listener in found}
        return [
            Alert(
                "NewListeningPort",
                PAGE,
                f"New listening TCP port {listener}, not in the allow-list",
                self._first_seen[listener],
                now + 3 * self._interval,
                {"address": listener.address, "port": str(listener.port)},
            )
            for listener in found
        ]
