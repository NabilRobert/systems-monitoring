"""Events → alerts: severities, labels, and burst counting."""

import ipaddress
from datetime import UTC, datetime, timedelta

from authwatch.alerts import EVENT_TTL, PAGE, TICKET
from authwatch.detect import MAX_COMMAND, BurstRules, Detector
from authwatch.parse import SSHFailure, SSHLogin, SudoCommand, SudoFailure

T0 = datetime(2026, 10, 28, 3, 0, 0, tzinfo=UTC)
RULES = BurstRules(
    per_source=5,
    per_source_window=timedelta(seconds=60),
    total=8,
    total_window=timedelta(minutes=10),
)


def failure(seconds: float, addr: str = "198.51.100.9", port: int | None = None) -> SSHFailure:
    port = port if port is not None else 40000 + int(seconds * 10)
    return SSHFailure(T0 + timedelta(seconds=seconds), "root", addr, port, f"line {addr} {port}")


def feed_all(detector: Detector, events: list[SSHFailure]):
    return [alert for event in events for alert in detector.feed(event, event.ts)]


def test_login_from_unknown_address_pages():
    detector = Detector(RULES, [ipaddress.ip_network("192.0.2.0/24")])
    login = SSHLogin(T0, "deploy", "publickey", "203.0.113.7", 5000, "raw-a")
    [alert] = detector.feed(login, T0)
    assert alert.name == "SSHLogin"
    assert alert.severity == PAGE
    assert alert.labels["known_source"] == "false"
    assert alert.labels["source"] == "203.0.113.7"
    assert "deploy (publickey) from 203.0.113.7" in alert.summary


def test_login_from_known_network_is_a_ticket():
    detector = Detector(RULES, [ipaddress.ip_network("192.0.2.0/24")])
    [alert] = detector.feed(SSHLogin(T0, "deploy", "publickey", "192.0.2.44", 1, "raw-b"), T0)
    assert alert.severity == TICKET
    assert alert.labels["known_source"] == "true"


def test_each_login_is_its_own_alert():
    detector = Detector(RULES)
    a = detector.feed(SSHLogin(T0, "u", "publickey", "203.0.113.7", 1, "raw-1"), T0)[0]
    b = detector.feed(SSHLogin(T0, "u", "publickey", "203.0.113.7", 2, "raw-2"), T0)[0]
    assert a.labels["event_id"] != b.labels["event_id"]


def test_one_shot_alerts_end_after_the_ttl_from_now_even_for_old_lines():
    detector = Detector(RULES)
    old = SSHLogin(T0, "u", "publickey", "203.0.113.7", 1, "raw")
    now = T0 + timedelta(hours=2)
    [alert] = detector.feed(old, now)
    assert alert.starts_at == T0
    assert alert.ends_at == now + EVENT_TTL


def test_sudo_command_pages_with_the_command():
    detector = Detector(RULES)
    [alert] = detector.feed(SudoCommand(T0, "arthur", "root", "/usr/bin/id", "raw"), T0)
    assert (alert.name, alert.severity) == ("SudoCommand", PAGE)
    assert alert.summary == "sudo: arthur ran as root: /usr/bin/id"


def test_long_sudo_command_is_shortened():
    detector = Detector(RULES)
    [alert] = detector.feed(SudoCommand(T0, "a", "root", "x" * 1000, "raw"), T0)
    command = alert.summary.split(": ", 2)[2]
    assert len(command) == MAX_COMMAND
    assert command.endswith("…")


def test_sudo_refusal_pages():
    detector = Detector(RULES)
    event = SudoFailure(T0, "mallory", "root", "/bin/bash", "3 incorrect password attempts", "r")
    [alert] = detector.feed(event, T0)
    assert (alert.name, alert.severity) == ("SudoAuthFailure", PAGE)
    assert "mallory" in alert.summary
    assert "3 incorrect password attempts" in alert.summary


def test_burst_fires_at_the_threshold_not_before():
    detector = Detector(RULES)
    below = feed_all(detector, [failure(s) for s in range(4)])
    assert below == []
    [alert] = feed_all(detector, [failure(4)])
    assert (alert.name, alert.severity) == ("SSHFailedLoginBurst", TICKET)
    assert alert.labels["source"] == "198.51.100.9"
    assert alert.summary == "5 failed SSH logins from 198.51.100.9 in 60 s"


def test_failures_spread_over_more_than_the_window_do_not_burst():
    detector = Detector(RULES)
    assert feed_all(detector, [failure(s * 20) for s in range(6)]) == []


def test_burst_counts_each_source_separately():
    detector = Detector(RULES)
    events = [failure(s, "198.51.100.1" if s % 2 else "198.51.100.2") for s in range(8)]
    assert [a for a in feed_all(detector, events) if a.name == "SSHFailedLoginBurst"] == []


def test_one_connection_counts_once():
    """Several lines about one connection (same address and port) are one attempt."""
    detector = Detector(RULES)
    events = [failure(s, port=4444) for s in range(10)]
    assert feed_all(detector, events) == []


def test_a_long_attack_alerts_once_per_window():
    detector = Detector(RULES)
    alerts = feed_all(detector, [failure(s * 0.5) for s in range(100)])  # 50 s of failures
    assert [a.name for a in alerts].count("SSHFailedLoginBurst") == 1
    later = feed_all(detector, [failure(70 + s * 0.5) for s in range(10)])
    assert [a.name for a in later].count("SSHFailedLoginBurst") == 1


def test_flood_counts_all_sources():
    detector = Detector(RULES)
    events = [failure(s * 30, f"198.51.100.{s}") for s in range(8)]  # 8 sources, 4 min
    alerts = feed_all(detector, events)
    [flood] = [a for a in alerts if a.name == "SSHFailedLoginFlood"]
    assert flood.severity == TICKET
    assert flood.summary == "8 failed SSH logins from 8 addresses in 10 min"


def test_flood_needs_the_threshold_inside_its_window():
    detector = Detector(RULES)
    events = [failure(s * 120, f"198.51.100.{s}") for s in range(8)]  # 8 over 14 min
    assert feed_all(detector, events) == []
