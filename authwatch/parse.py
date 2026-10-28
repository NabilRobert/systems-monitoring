"""Turn auth-log lines into security events.

Two line formats are understood:
- RFC 3339, as rsyslog writes by default on current Ubuntu and as
  `journalctl -o short-iso` prints:
  `2026-10-28T10:00:01.123456+07:00 host sshd[123]: message`
- classic syslog, as older systems write:
  `Oct 28 10:00:01 host sshd[123]: message`

Lines from other programs, and messages no rule needs, give no event.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

_RFC3339 = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))"
    r"\s+(?P<host>\S+)\s+(?P<prog>[^\s\[:]+)(?:\[\d+\])?:\s?(?P<msg>.*)$"
)
_CLASSIC = re.compile(
    r"^(?P<ts>[A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})"
    r"\s+(?P<host>\S+)\s+(?P<prog>[^\s\[:]+)(?:\[\d+\])?:\s?(?P<msg>.*)$"
)

# OpenSSH 9.8 and later log authentication from a per-connection
# `sshd-session` process; earlier versions from `sshd`.
_SSHD = ("sshd", "sshd-session")

_ACCEPTED = re.compile(
    r"^Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<addr>\S+) port (?P<port>\d+)"
)
# A failed password for an *invalid* user is skipped here: the same
# connection also logs "Invalid user", which is counted instead.
_FAILED = re.compile(
    r"^Failed \S+ for (?P<invalid>invalid user )?(?P<user>\S+) from (?P<addr>\S+)"
    r"(?: port (?P<port>\d+))?"
)
_INVALID = re.compile(r"^Invalid user (?P<user>\S*) from (?P<addr>\S+)(?: port (?P<port>\d+))?")
# With key-only SSH, a refused key logs only this, at disconnect.
_CLOSED_PREAUTH = re.compile(
    r"^(?:Connection closed by|Disconnected from) (?:authenticating|invalid) user (?P<user>\S*) "
    r"(?P<addr>\S+) port (?P<port>\d+) \[preauth\]"
)

# sudo: "arthur : TTY=pts/0 ; PWD=/home/arthur ; USER=root ; COMMAND=/usr/bin/id"
# A refusal puts its reason before TTY: "arthur : 3 incorrect password attempts ; TTY=…"
_SUDO = re.compile(
    r"^\s*(?P<user>\S+) : (?:(?P<reason>[^;]*?) ; )?TTY=(?P<tty>\S+) ; PWD=.*? ; "
    r"USER=(?P<run_as>\S+) ;(?: [A-Z]+=.*? ;)* COMMAND=(?P<command>.*)$"
)


@dataclass(frozen=True, slots=True)
class SSHLogin:
    ts: datetime
    user: str
    method: str
    addr: str
    port: int
    raw: str


@dataclass(frozen=True, slots=True)
class SSHFailure:
    ts: datetime
    user: str
    addr: str
    port: int | None
    raw: str


@dataclass(frozen=True, slots=True)
class SudoCommand:
    ts: datetime
    user: str
    run_as: str
    command: str
    raw: str


@dataclass(frozen=True, slots=True)
class SudoFailure:
    ts: datetime
    user: str
    run_as: str
    command: str
    reason: str
    raw: str


Event = SSHLogin | SSHFailure | SudoCommand | SudoFailure


def parse_timestamp(text: str, now: datetime, local: tzinfo) -> datetime:
    """Parse either timestamp format into an aware datetime.

    Classic syslog has no year or zone: the year is taken from `now`, and a
    date more than a day ahead of `now` is taken to be last year's (a line
    from 31 December read on 1 January).
    """
    if text[0].isdigit():
        return datetime.fromisoformat(text)
    parsed = datetime.strptime(f"{now.year} {' '.join(text.split())}", "%Y %b %d %H:%M:%S")
    parsed = parsed.replace(tzinfo=local)
    if parsed > now + timedelta(days=1):
        parsed = parsed.replace(year=now.year - 1)
    return parsed


def parse_line(line: str, now: datetime, local: tzinfo) -> Event | None:
    """Return the security event in one log line, or None."""
    line = line.rstrip("\r\n")
    head = _RFC3339.match(line) or _CLASSIC.match(line)
    if head is None:
        return None
    prog, msg = head["prog"], head["msg"]
    if prog not in _SSHD and prog != "sudo":
        return None
    ts = parse_timestamp(head["ts"], now, local)
    if prog in _SSHD:
        return _parse_sshd(msg, ts, line)
    return _parse_sudo(msg, ts, line)


def _port(text: str | None) -> int | None:
    return int(text) if text else None


def _parse_sshd(msg: str, ts: datetime, raw: str) -> Event | None:
    if m := _ACCEPTED.match(msg):
        return SSHLogin(ts, m["user"], m["method"], m["addr"], int(m["port"]), raw)
    if m := _FAILED.match(msg):
        if m["invalid"]:
            return None
        return SSHFailure(ts, m["user"], m["addr"], _port(m["port"]), raw)
    if m := _INVALID.match(msg):
        return SSHFailure(ts, m["user"], m["addr"], _port(m["port"]), raw)
    if m := _CLOSED_PREAUTH.match(msg):
        return SSHFailure(ts, m["user"], m["addr"], int(m["port"]), raw)
    return None


def _parse_sudo(msg: str, ts: datetime, raw: str) -> Event | None:
    m = _SUDO.match(msg)
    if m is None:
        return None
    if m["reason"]:
        return SudoFailure(ts, m["user"], m["run_as"], m["command"], m["reason"], raw)
    return SudoCommand(ts, m["user"], m["run_as"], m["command"], raw)
