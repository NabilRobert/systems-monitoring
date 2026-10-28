"""Auth-log lines → events. Addresses are documentation ranges (RFC 5737, 3849)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from authwatch.parse import (
    SSHFailure,
    SSHLogin,
    SudoCommand,
    SudoFailure,
    parse_line,
    parse_timestamp,
)

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
WIB = timezone(timedelta(hours=7))


def parse(line: str):
    return parse_line(line, NOW, WIB)


def test_accepted_publickey_rfc3339():
    event = parse(
        "2026-10-28T10:00:01.123456+07:00 web-1 sshd[812]: Accepted publickey for deploy "
        "from 203.0.113.7 port 51522 ssh2: ED25519 SHA256:abc"
    )
    assert isinstance(event, SSHLogin)
    assert (event.user, event.method, event.addr, event.port) == (
        "deploy",
        "publickey",
        "203.0.113.7",
        51522,
    )
    assert event.ts == datetime(2026, 10, 28, 10, 0, 1, 123456, tzinfo=WIB)


def test_accepted_password_classic_syslog_uses_local_zone_and_this_year():
    event = parse(
        "Oct 28 09:15:00 web-1 sshd[9]: Accepted password for arthur from 2001:db8::5 port 2222 ssh2"
    )
    assert isinstance(event, SSHLogin)
    assert (event.method, event.addr) == ("password", "2001:db8::5")
    assert event.ts == datetime(2026, 10, 28, 9, 15, tzinfo=WIB)


def test_openssh_9_8_sshd_session_program():
    event = parse(
        "2026-10-28T10:00:01+07:00 web-1 sshd-session[90]: Accepted publickey for deploy "
        "from 203.0.113.7 port 51522 ssh2"
    )
    assert isinstance(event, SSHLogin)


def test_journalctl_short_iso_offset_without_colon():
    event = parse(
        "2026-10-28T10:00:01+0700 web-1 sshd[1]: Accepted publickey for a from 192.0.2.1 port 1 ssh2"
    )
    assert isinstance(event, SSHLogin)
    assert event.ts.utcoffset() == timedelta(hours=7)


def test_classic_date_after_new_year_is_last_year():
    now = datetime(2027, 1, 1, 0, 5, tzinfo=WIB)
    assert parse_timestamp("Dec 31 23:59:00", now, WIB).year == 2026
    assert parse_timestamp("Jan  1 00:04:00", now, WIB).year == 2027


@pytest.mark.parametrize(
    ("message", "user", "addr", "port"),
    [
        ("Failed password for root from 198.51.100.9 port 4001 ssh2", "root", "198.51.100.9", 4001),
        ("Invalid user admin from 198.51.100.9 port 4002", "admin", "198.51.100.9", 4002),
        ("Invalid user  from 198.51.100.9 port 4003", "", "198.51.100.9", 4003),
        (
            "Connection closed by authenticating user root 198.51.100.9 port 4004 [preauth]",
            "root",
            "198.51.100.9",
            4004,
        ),
        (
            "Disconnected from invalid user oracle 198.51.100.9 port 4005 [preauth]",
            "oracle",
            "198.51.100.9",
            4005,
        ),
    ],
)
def test_failed_logins(message: str, user: str, addr: str, port: int):
    event = parse(f"2026-10-28T10:00:00+07:00 web-1 sshd[7]: {message}")
    assert isinstance(event, SSHFailure)
    assert (event.user, event.addr, event.port) == (user, addr, port)


def test_failed_password_for_invalid_user_is_left_to_the_invalid_user_line():
    line = (
        "2026-10-28T10:00:00+07:00 web-1 sshd[7]: Failed password for invalid user admin "
        "from 198.51.100.9 port 4002 ssh2"
    )
    assert parse(line) is None


def test_sudo_command():
    event = parse(
        "2026-10-28T10:00:00+07:00 web-1 sudo:   arthur : TTY=pts/0 ; PWD=/home/arthur ; "
        "USER=root ; COMMAND=/usr/bin/systemctl restart caddy"
    )
    assert isinstance(event, SudoCommand)
    assert (event.user, event.run_as, event.command) == (
        "arthur",
        "root",
        "/usr/bin/systemctl restart caddy",
    )


def test_sudo_with_pid_and_env_field():
    event = parse(
        "2026-10-28T10:00:00+07:00 web-1 sudo[4411]:   arthur : TTY=pts/1 ; PWD=/ ; "
        "USER=root ; ENV=LANG=C ; COMMAND=/usr/bin/id"
    )
    assert isinstance(event, SudoCommand)
    assert event.command == "/usr/bin/id"


@pytest.mark.parametrize(
    "reason",
    ["3 incorrect password attempts", "1 incorrect password attempt", "user NOT in sudoers"],
)
def test_sudo_refused(reason: str):
    event = parse(
        f"2026-10-28T10:00:00+07:00 web-1 sudo:     mallory : {reason} ; TTY=pts/2 ; "
        "PWD=/tmp ; USER=root ; COMMAND=/bin/bash"
    )
    assert isinstance(event, SudoFailure)
    assert (event.user, event.reason, event.command) == ("mallory", reason, "/bin/bash")


@pytest.mark.parametrize(
    "line",
    [
        "2026-10-28T10:00:00+07:00 web-1 sshd[7]: Received disconnect from 192.0.2.4 port 22:11",
        (
            "2026-10-28T10:00:00+07:00 web-1 sshd[7]: pam_unix(sshd:session): session opened for "
            "user deploy(uid=1000)"
        ),
        (
            "2026-10-28T10:00:00+07:00 web-1 sudo: pam_unix(sudo:session): session opened for "
            "user root(uid=0) by arthur(uid=1000)"
        ),
        "2026-10-28T10:00:00+07:00 web-1 CRON[5]: Accepted publickey for x from 192.0.2.1 port 1",
        "not a log line at all",
        "",
    ],
)
def test_lines_without_events(line: str):
    assert parse(line) is None
