"""Run authwatch.

python -m authwatch              watch the log and the ports (the service)
python -m authwatch list-ports   print the listeners the allow-list must cover
python -m authwatch test-alert   send one test alert, to check delivery
"""

import logging
import queue
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from authwatch import config
from authwatch.alerts import EVENT_TTL, PAGE, Alert
from authwatch.detect import Detector
from authwatch.follow import Follower
from authwatch.parse import parse_line
from authwatch.ports import PortWatcher, read_listeners
from authwatch.sender import Sender

log = logging.getLogger("authwatch")


def _now() -> datetime:
    return datetime.now(UTC)


def _stdin_lines() -> Callable[[], list[str]]:
    """Read standard input on a thread, so a quiet journal doesn't stall the port checks."""
    lines: queue.Queue[str] = queue.Queue()

    def pump() -> None:
        for line in sys.stdin:
            lines.put(line)

    threading.Thread(target=pump, daemon=True).start()

    def drain() -> list[str]:
        out: list[str] = []
        while True:
            try:
                out.append(lines.get_nowait())
            except queue.Empty:
                return out

    return drain


def run(cfg: config.Config) -> None:
    local = datetime.now().astimezone().tzinfo or UTC
    detector = Detector(cfg.bursts, cfg.known_networks)
    ports = PortWatcher(cfg.allowed_ports, cfg.port_interval, cfg.ignore_loopback)
    sender = Sender(cfg.alertmanager_url, cfg.host_label, cfg.runbook_base)
    if cfg.log_file == "-":
        read_lines = _stdin_lines()
    else:
        read_lines = Follower(Path(cfg.log_file), from_start=cfg.from_start).poll
    log.info(
        "watching %s and %s; allowed ports: %s",
        cfg.log_file,
        cfg.proc_net,
        ", ".join(
            str(a.port) if a.address is None else f"{a.address}:{a.port}" for a in cfg.allowed_ports
        ),
    )
    next_ports = _now()
    while True:
        now = _now()
        for line in read_lines():
            event = parse_line(line, now, local)
            if event is not None:
                alerts = detector.feed(event, now)
                for alert in alerts:
                    log.info("%s: %s", alert.name, alert.summary)
                sender.enqueue(alerts)
        if now >= next_ports:
            sender.enqueue(ports.check(read_listeners(cfg.proc_net), now))
            next_ports = now + cfg.port_interval
        sender.flush(now)
        if cfg.alive_file is not None:
            cfg.alive_file.touch()
        time.sleep(cfg.poll_interval)


def list_ports(cfg: config.Config) -> None:
    watcher = PortWatcher(cfg.allowed_ports, cfg.port_interval, cfg.ignore_loopback)
    listeners = read_listeners(cfg.proc_net)
    unexpected = set(watcher.unexpected(listeners))
    for listener in sorted(listeners):
        if listener.is_loopback:
            status = "loopback (ignored)" if cfg.ignore_loopback else "loopback"
        else:
            status = "NOT ALLOWED" if listener in unexpected else "allowed"
        print(f"{listener!s:<45} {status}")


def test_alert(cfg: config.Config) -> int:
    now = _now()
    sender = Sender(cfg.alertmanager_url, cfg.host_label, cfg.runbook_base)
    sender.enqueue(
        [
            Alert(
                "AuthwatchTest",
                PAGE,
                "Test alert from authwatch: delivery works",
                now,
                now + EVENT_TTL,
                {"event_id": now.isoformat()},
            )
        ]
    )
    if sender.flush(now):
        print("sent; it should arrive within about a minute")
        return 0
    print("could not reach Alertmanager at", cfg.alertmanager_url, file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = config.load()
    command = argv[0] if argv else "run"
    if command == "run":
        run(cfg)
        return 0
    if command == "list-ports":
        list_ports(cfg)
        return 0
    if command == "test-alert":
        return test_alert(cfg)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
