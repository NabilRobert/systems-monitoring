"""Socket tables → listeners → alerts. Fixtures are from a throwaway container."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from authwatch.alerts import PAGE
from authwatch.ports import Allowed, Listener, PortWatcher, parse_proc_net_tcp, read_listeners

FIXTURES = Path(__file__).parent / "fixtures"
T0 = datetime(2026, 10, 28, 3, 0, tzinfo=UTC)
INTERVAL = timedelta(seconds=30)


def fixture_dir(tmp_path: Path) -> Path:
    (tmp_path / "tcp").write_text((FIXTURES / "proc_net_tcp").read_text())
    (tmp_path / "tcp6").write_text((FIXTURES / "proc_net_tcp6").read_text())
    return tmp_path


def test_parses_only_listening_sockets_v4():
    listeners = parse_proc_net_tcp((FIXTURES / "proc_net_tcp").read_text())
    assert listeners == {Listener("127.0.0.1", 5432), Listener("0.0.0.0", 22)}


def test_parses_v6():
    listeners = parse_proc_net_tcp((FIXTURES / "proc_net_tcp6").read_text())
    assert listeners == {Listener("::1", 9093), Listener("::", 443)}


def test_reads_both_tables(tmp_path: Path):
    assert len(read_listeners(fixture_dir(tmp_path))) == 4


def test_missing_tables_are_empty(tmp_path: Path):
    assert read_listeners(tmp_path) == set()


def test_allow_list_entries():
    assert Allowed.parse("22") == Allowed(22)
    assert Allowed.parse("10.0.0.5:8080") == Allowed(8080, "10.0.0.5")
    assert Allowed.parse("[2001:db8::1]:9000") == Allowed(9000, "2001:db8::1")
    assert Allowed(22).matches(Listener("::", 22))
    assert not Allowed(8080, "10.0.0.5").matches(Listener("0.0.0.0", 8080))


def test_loopback_is_ignored_by_default_and_allowed_ports_pass(tmp_path: Path):
    watcher = PortWatcher([Allowed(22)], INTERVAL)
    [alert] = watcher.check(read_listeners(fixture_dir(tmp_path)), T0)
    assert (alert.name, alert.severity) == ("NewListeningPort", PAGE)
    assert alert.labels == {"address": "::", "port": "443"}
    assert alert.summary == "New listening TCP port [::]:443, not in the allow-list"


def test_loopback_can_be_watched_too(tmp_path: Path):
    watcher = PortWatcher([Allowed(22), Allowed(443)], INTERVAL, ignore_loopback=False)
    alerts = watcher.check(read_listeners(fixture_dir(tmp_path)), T0)
    assert sorted(a.labels["port"] for a in alerts) == ["5432", "9093"]


def test_ipv4_mapped_loopback_counts_as_loopback():
    assert Listener("::ffff:127.0.0.1", 80).is_loopback
    assert not Listener("::ffff:192.0.2.1", 80).is_loopback


def test_alert_keeps_firing_while_open_and_keeps_its_start():
    watcher = PortWatcher([], INTERVAL)
    open_port = {Listener("0.0.0.0", 8080)}
    [first] = watcher.check(open_port, T0)
    [second] = watcher.check(open_port, T0 + INTERVAL)
    assert second.starts_at == first.starts_at == T0
    assert second.ends_at == T0 + INTERVAL + 3 * INTERVAL


def test_closed_port_stops_and_a_reopen_starts_fresh():
    watcher = PortWatcher([], INTERVAL)
    port = {Listener("0.0.0.0", 8080)}
    watcher.check(port, T0)
    assert watcher.check(set(), T0 + INTERVAL) == []
    [again] = watcher.check(port, T0 + 2 * INTERVAL)
    assert again.starts_at == T0 + 2 * INTERVAL
