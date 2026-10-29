"""End to end: an auth-log line or socket table → Vector → Alertmanager → the
Telegram stand-in. Needs Docker; run with `uv run pytest -m e2e e2e/`."""

import json
import shlex
import time
from datetime import timedelta
from pathlib import Path

import pytest

from e2e.stack import (
    OUT,
    ROOT,
    TCP_BASE,
    TCP_NEW_PORT,
    append,
    check,
    compose,
    line,
    parse_go_time,
    text_of,
    wait_for,
    write_atomic,
)

pytestmark = pytest.mark.e2e


def test_ssh_login_pages(stack: Path):
    written = append(line("Accepted publickey for deploy from 203.0.113.7 port 51522 ssh2"))
    message = wait_for("SSH login: deploy (publickey) from 203.0.113.7")
    check(message, written, silent=False)
    text = text_of(message)
    assert text.startswith("🔴 <b>SSHLogin</b> on e2e-host")
    assert "Runbook: https://example.org/runbooks/ssh-login.md" in text


def test_login_from_known_network_is_silent(stack: Path):
    written = append(line("Accepted publickey for arthur from 192.0.2.10 port 40000 ssh2"))
    check(wait_for("SSH login: arthur (publickey) from 192.0.2.10"), written, silent=True)


def test_sudo_command_pages_and_is_escaped(stack: Path):
    written = append(
        line(
            "  arthur : TTY=pts/0 ; PWD=/home/arthur ; USER=root ; "
            "COMMAND=/usr/bin/grep <b>x</b> /etc/hosts",
            program="sudo",
        )
    )
    message = wait_for("sudo: arthur ran as root")
    check(message, written, silent=False)
    assert "&lt;b&gt;x&lt;/b&gt;" in text_of(message)


def test_sudo_refusal_pages(stack: Path):
    written = append(
        line(
            "  mallory : 3 incorrect password attempts ; TTY=pts/2 ; PWD=/tmp ; "
            "USER=root ; COMMAND=/bin/bash",
            program="sudo",
        )
    )
    check(wait_for("sudo refused for mallory"), written, silent=False)


def test_failed_login_burst_is_a_silent_ticket(stack: Path):
    lines = [line(f"Invalid user admin{n} from 198.51.100.66 port {50000 + n}") for n in range(20)]
    written = append(*lines)
    message = wait_for("20 failed SSH logins from 198.51.100.66 in 60 s")
    check(message, written, silent=True)
    assert text_of(message).startswith("🟡 <b>SSHFailedLoginBurst</b>")


def test_failed_login_flood_is_a_silent_ticket(stack: Path):
    lines = [line(f"Invalid user u from 198.51.100.{n % 200} port {20000 + n}") for n in range(200)]
    written = append(*lines)
    # The 20 failures of the burst test count too, so the threshold (200)
    # is crossed partway through these lines.
    message = wait_for("<b>SSHFailedLoginFlood</b>")
    check(message, written, silent=True)
    assert "200 failed SSH logins from" in text_of(message)
    assert "addresses in 10 min" in text_of(message)


def test_new_listening_port_pages_then_resolves(stack: Path):
    write_atomic(OUT / "net" / "tcp", TCP_NEW_PORT)
    written = time.time()
    message = wait_for("New listening TCP port 0.0.0.0:8080", timeout=120)
    check(message, written, silent=False)
    write_atomic(OUT / "net" / "tcp", TCP_BASE)
    resolved = wait_for("✅ Resolved: <b>NewListeningPort</b>", timeout=240)
    assert "resolved: New listening TCP port 0.0.0.0:8080" in text_of(resolved)


def test_hand_sent_delivery_test_arrives(stack: Path):
    """The drill in docs/runbooks/test-alert.md, with the same amtool command."""
    runbook = (ROOT / "docs" / "runbooks" / "test-alert.md").read_text()
    command = next(row for row in runbook.splitlines() if row.startswith("docker compose exec"))
    args = command.split(" exec ", 1)[1]
    sent_at = time.time()
    compose("exec", "-T", *shlex.split(args.replace('"$(date +%s)"', "e2e-drill")))
    check(wait_for("Test alert: delivery works"), sent_at, silent=False)


def test_a_login_right_after_log_rotation_still_alerts(stack: Path):
    """logrotate renames the log and creates a new one; sshd may write to it at once."""
    log = OUT / "log" / "auth.log"
    log.rename(OUT / "log" / "auth.log.1")
    log.write_text(line("Accepted publickey for rotated from 203.0.113.21 port 3001 ssh2"))
    written = time.time()
    check(wait_for("SSH login: rotated (publickey) from 203.0.113.21"), written, silent=False)
    # And the next line in the new file too.
    written = append(line("Accepted publickey for rotated2 from 203.0.113.22 port 3002 ssh2"))
    check(wait_for("SSH login: rotated2 (publickey) from 203.0.113.22"), written, silent=False)


def test_a_login_during_an_alertmanager_outage_arrives_afterwards(stack: Path):
    """Vector keeps the alert and retries; Alertmanager times it from when it arrives."""
    compose("stop", "alertmanager")
    append(line("Accepted publickey for outage from 203.0.113.31 port 3101 ssh2"))
    time.sleep(20)
    restarted = time.time()
    compose("start", "alertmanager")
    message = wait_for("SSH login: outage (publickey) from 203.0.113.31", timeout=120)
    assert float(message["received_at"]) >= restarted  # pyright: ignore[reportArgumentType]
    # The event carried no end time, so Alertmanager set one 5 minutes after
    # it *received* it: an event buffered through a longer outage would not
    # arrive already over (ADR-006).
    query = ["exec", "-T", "alertmanager", "amtool", "alert", "query", "user=outage",
             "--output=json", "--alertmanager.url=http://127.0.0.1:9093"]  # fmt: skip
    [alert] = json.loads(compose(*query))
    starts = parse_go_time(alert["startsAt"])
    assert parse_go_time(alert["endsAt"]) - starts == timedelta(minutes=5)
    assert starts.timestamp() >= restarted - 2
