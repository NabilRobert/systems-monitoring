"""Rules: which events become alerts, and at what severity."""

import hashlib
import ipaddress
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from authwatch.alerts import EVENT_TTL, PAGE, TICKET, Alert
from authwatch.parse import Event, SSHFailure, SSHLogin, SudoCommand, SudoFailure

Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# A sudo command can be long; the message only needs enough to recognise it.
MAX_COMMAND = 200


@dataclass(frozen=True, slots=True)
class BurstRules:
    per_source: int = 20
    per_source_window: timedelta = timedelta(seconds=60)
    total: int = 200
    total_window: timedelta = timedelta(minutes=10)


class Detector:
    """Feed events in log order; get back the alerts they raise."""

    def __init__(self, bursts: BurstRules, known_networks: list[Network] | None = None) -> None:
        self._bursts = bursts
        self._known = known_networks or []
        # Failed connections, as (time, source address, connection key).
        # One connection can log several failure lines; it counts once.
        self._failures: deque[tuple[datetime, str, str]] = deque()
        self._seen: set[str] = set()
        # When each burst alert last fired, so a long attack alerts once per
        # window rather than once per line.
        self._source_fired: dict[str, datetime] = {}
        self._flood_fired: datetime | None = None

    def feed(self, event: Event, now: datetime) -> list[Alert]:
        ends_at = max(event.ts, now) + EVENT_TTL
        match event:
            case SSHLogin():
                return [self._login(event, ends_at)]
            case SudoCommand():
                command = _shorten(event.command)
                return [
                    Alert(
                        "SudoCommand",
                        PAGE,
                        f"sudo: {event.user} ran as {event.run_as}: {command}",
                        event.ts,
                        ends_at,
                        {"user": event.user, "event_id": _event_id(event.raw)},
                    )
                ]
            case SudoFailure():
                return [
                    Alert(
                        "SudoAuthFailure",
                        PAGE,
                        f"sudo refused for {event.user} ({event.reason}): "
                        f"{_shorten(event.command)}",
                        event.ts,
                        ends_at,
                        {"user": event.user, "event_id": _event_id(event.raw)},
                    )
                ]
            case SSHFailure():
                return self._failure(event, ends_at)

    def _login(self, event: SSHLogin, ends_at: datetime) -> Alert:
        known = self._is_known(event.addr)
        where = "a known network" if known else "an unknown address"
        return Alert(
            "SSHLogin",
            TICKET if known else PAGE,
            f"SSH login: {event.user} ({event.method}) from {event.addr}, {where}",
            event.ts,
            ends_at,
            {
                "user": event.user,
                "source": event.addr,
                "known_source": "true" if known else "false",
                "event_id": _event_id(event.raw),
            },
        )

    def _is_known(self, addr: str) -> bool:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in net for net in self._known)

    def _failure(self, event: SSHFailure, ends_at: datetime) -> list[Alert]:
        key = f"{event.addr}:{event.port}" if event.port is not None else event.raw
        self._expire(event.ts)
        if key in self._seen:
            return []
        self._seen.add(key)
        self._failures.append((event.ts, event.addr, key))

        rules = self._bursts
        alerts: list[Alert] = []
        source_since = event.ts - rules.per_source_window
        from_source = sum(
            1 for ts, addr, _ in self._failures if addr == event.addr and ts > source_since
        )
        last = self._source_fired.get(event.addr)
        if from_source >= rules.per_source and (
            last is None or event.ts - last >= rules.per_source_window
        ):
            self._source_fired[event.addr] = event.ts
            alerts.append(
                Alert(
                    "SSHFailedLoginBurst",
                    TICKET,
                    f"{from_source} failed SSH logins from {event.addr} in "
                    f"{_seconds(rules.per_source_window)}",
                    event.ts,
                    ends_at,
                    {"source": event.addr, "event_id": _event_id(f"burst {key} {event.ts}")},
                )
            )

        total_since = event.ts - rules.total_window
        total = sum(1 for ts, _, _ in self._failures if ts > total_since)
        last = self._flood_fired
        if total >= rules.total and (last is None or event.ts - last >= rules.total_window):
            self._flood_fired = event.ts
            sources = len({addr for ts, addr, _ in self._failures if ts > total_since})
            alerts.append(
                Alert(
                    "SSHFailedLoginFlood",
                    TICKET,
                    f"{total} failed SSH logins from {sources} addresses in "
                    f"{_seconds(rules.total_window)}",
                    event.ts,
                    ends_at,
                    {"event_id": _event_id(f"flood {event.ts}")},
                )
            )
        return alerts

    def _expire(self, now: datetime) -> None:
        keep = max(self._bursts.per_source_window, self._bursts.total_window)
        while self._failures and self._failures[0][0] <= now - keep:
            _, _, key = self._failures.popleft()
            self._seen.discard(key)
        stale = [addr for addr, ts in self._source_fired.items() if ts <= now - keep]
        for addr in stale:
            del self._source_fired[addr]


def _event_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _shorten(command: str) -> str:
    return command if len(command) <= MAX_COMMAND else command[: MAX_COMMAND - 1] + "…"


def _seconds(window: timedelta) -> str:
    seconds = int(window.total_seconds())
    return f"{seconds // 60} min" if seconds % 60 == 0 and seconds >= 120 else f"{seconds} s"
