"""End to end in Docker: log line → detector → Alertmanager → Telegram stand-in.

Runs the production compose file with e2e/compose.override.yaml on top, so
the images, hardening, memory caps and routing tree are the real ones.
Needs Docker. Run with `uv run pytest -m e2e e2e/` (about 3 minutes).
Addresses are documentation ranges (RFC 5737).
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import time
import urllib.parse
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parent.parent
OUT = ROOT / "e2e" / "out"
FIXTURES = ROOT / "tests" / "fixtures"
# Compose reads HOST_LABEL for vmalert's host label, as from deploy/.env on
# the server.
COMPOSE_ENV = {**os.environ, "HOST_LABEL": "e2e-host"}
COMPOSE = [
    "docker",
    "compose",
    "-f",
    str(ROOT / "deploy" / "compose.yaml"),
    "-f",
    str(ROOT / "e2e" / "compose.override.yaml"),
]
WIB = timezone(timedelta(hours=7))
CHAT_ID = 424242
# Phase 1, metric 3: a security event reaches the channel within 60 s.
MAX_LATENCY = 60.0

# 0.0.0.0:22 listening, plus loopback listeners (ignored).
TCP_BASE = (FIXTURES / "proc_net_tcp").read_text()
# The same, plus 0.0.0.0:8080 (0x1F90) listening: a new, unexpected port.
TCP_NEW_PORT = TCP_BASE + (
    "   4: 00000000:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000"
    "     0        0 9999999 1 0000000000000000 100 0 0 10 0\n"
)


def line(message: str, program: str = "sshd[812]") -> str:
    ts = datetime.now(WIB).isoformat(timespec="microseconds")
    return f"{ts} e2e-host {program}: {message}\n"


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def messages() -> list[dict[str, object]]:
    path = OUT / "messages" / "messages.jsonl"
    if not path.exists():
        return []
    return [json.loads(row) for row in path.read_text().splitlines()]


def text_of(message: dict[str, object]) -> str:
    body = message["body"]
    assert isinstance(body, dict)
    return str(body["text"])  # pyright: ignore[reportUnknownArgumentType]


def wait_for(predicate_text: str, timeout: float = 90.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for message in messages():
            if predicate_text in text_of(message):
                return message
        time.sleep(1)
    seen = "\n---\n".join(text_of(m) for m in messages())
    raise AssertionError(f"no message containing {predicate_text!r} in {timeout} s. Seen:\n{seen}")


@pytest.fixture(scope="module")
def stack() -> Iterator[Path]:
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ("log", "net", "messages", "secrets"):
        (OUT / sub).mkdir(parents=True)
    (OUT / "messages").chmod(0o777)
    (OUT / "secrets" / "telegram_bot_token").write_text("123456:dummy-token-for-e2e\n")
    (OUT / "secrets" / "telegram_chat_id").write_text(f"{CHAT_ID}\n")
    production = (ROOT / "deploy" / "alertmanager" / "alertmanager.yml").read_text()
    assert production.count("api_url: https://api.telegram.org") == 1
    (OUT / "alertmanager.yml").write_text(
        production.replace(
            "api_url: https://api.telegram.org", "api_url: http://telegram-stub:8080"
        )
    )
    write_atomic(OUT / "net" / "tcp", TCP_BASE)
    # A line already in the log before the detector starts: must never alert.
    (OUT / "log" / "auth.log").write_text(
        line("Accepted publickey for oldsession from 203.0.113.99 port 1 ssh2")
    )
    subprocess.run(
        [*COMPOSE, "up", "-d", "--build", "--wait"], check=True, cwd=ROOT, env=COMPOSE_ENV
    )
    try:
        yield OUT
    finally:
        if not messages():
            subprocess.run([*COMPOSE, "logs", "--no-color"], check=False, cwd=ROOT, env=COMPOSE_ENV)
        subprocess.run(
            [*COMPOSE, "down", "-v", "--remove-orphans"], check=True, cwd=ROOT, env=COMPOSE_ENV
        )


def append(*lines: str) -> float:
    with (OUT / "log" / "auth.log").open("a") as f:
        f.writelines(lines)
    return time.time()


def check(message: dict[str, object], written_at: float, silent: bool) -> None:
    body = message["body"]
    assert isinstance(body, dict)
    assert str(body["chat_id"]) == str(CHAT_ID)  # pyright: ignore[reportUnknownArgumentType]
    assert body["parse_mode"] == "HTML"
    assert bool(body.get("disable_notification", False)) is silent  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    latency = float(message["received_at"]) - written_at  # pyright: ignore[reportArgumentType]
    with (OUT / "latency.txt").open("a") as f:
        f.write(f"{text_of(message).splitlines()[0]}\t{latency:.1f}\n")
    assert latency < MAX_LATENCY, f"took {latency:.1f} s"


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
    subprocess.run(
        [*COMPOSE, "exec", "-T", *shlex.split(args.replace('"$(date +%s)"', "e2e-drill"))],
        check=True,
        cwd=ROOT,
        env=COMPOSE_ENV,
    )
    check(wait_for("Test alert: delivery works"), sent_at, silent=False)


def query_metrics(promql: str) -> list[dict[str, object]]:
    """An instant query to VictoriaMetrics, from inside the compose network."""
    url = "http://victoriametrics:8428/api/v1/query?query=" + urllib.parse.quote(promql)
    out = subprocess.run(
        [*COMPOSE, "exec", "-T", "vector", "wget", "-q", "-O", "-", url],
        check=True, cwd=ROOT, env=COMPOSE_ENV, capture_output=True, text=True,
    ).stdout  # fmt: skip
    result = json.loads(out)["data"]["result"]
    assert isinstance(result, list)
    return result  # pyright: ignore[reportUnknownVariableType]


def wait_for_metric(promql: str, timeout: float = 90.0) -> list[dict[str, object]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = query_metrics(promql)
        if result:
            return result
        time.sleep(5)
    raise AssertionError(f"no result for {promql!r} in {timeout} s")


def test_host_metrics_from_vector_reach_victoriametrics(stack: Path):
    assert wait_for_metric("host_load1")
    assert wait_for_metric('host_filesystem_used_ratio{mountpoint="/"}')
    assert wait_for_metric("host_memory_oom_kill_events_total")
    # The real hostname is dropped; alerts carry HOST_LABEL instead.
    assert query_metrics('count({__name__=~"host_.+", host!=""})') == []


def test_probes_of_a_healthy_app_succeed(stack: Path):
    [result] = wait_for_metric('probe_success{app="demo-app"}')
    value = result["value"]
    assert isinstance(value, list)
    assert value[1] == "1"  # pyright: ignore[reportUnknownMemberType]


def test_vmalert_records_the_slo_error_ratios(stack: Path):
    # Proves vmalert is running and writing its recording rules back.
    assert wait_for_metric('app:probe_error:ratio_5m{app="demo-app"}', timeout=120)


def test_app_down_pages_then_resolves(stack: Path):
    subprocess.run([*COMPOSE, "stop", "demo-app"], check=True, cwd=ROOT, env=COMPOSE_ENV)
    stopped_at = time.time()
    # 3 minutes of failed probes, plus scrape, evaluation and grouping.
    message = wait_for("<b>AppDown</b> on e2e-host", timeout=360)
    assert "demo-app is down: every probe of http://demo-app:8080/health failed" in text_of(message)
    took = float(message["received_at"]) - stopped_at  # pyright: ignore[reportArgumentType]
    with (OUT / "latency.txt").open("a") as f:
        f.write(f"AppDown after stopping the app\t{took:.1f}\n")
    subprocess.run([*COMPOSE, "start", "demo-app"], check=True, cwd=ROOT, env=COMPOSE_ENV)
    wait_for("✅ Resolved: <b>AppDown</b>", timeout=240)


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


def _parse_go_time(text: str) -> datetime:
    """Go prints up to 9 fractional digits; Python's parser takes at most 6."""
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", text))


def test_a_login_during_an_alertmanager_outage_arrives_afterwards(stack: Path):
    """Vector keeps the alert and retries; Alertmanager times it from when it arrives."""
    subprocess.run([*COMPOSE, "stop", "alertmanager"], check=True, cwd=ROOT, env=COMPOSE_ENV)
    append(line("Accepted publickey for outage from 203.0.113.31 port 3101 ssh2"))
    time.sleep(20)
    restarted = time.time()
    subprocess.run([*COMPOSE, "start", "alertmanager"], check=True, cwd=ROOT, env=COMPOSE_ENV)
    message = wait_for("SSH login: outage (publickey) from 203.0.113.31", timeout=120)
    assert float(message["received_at"]) >= restarted  # pyright: ignore[reportArgumentType]
    # The event carried no end time, so Alertmanager set one 5 minutes after
    # it *received* it: an event buffered through a longer outage would not
    # arrive already over (ADR-006).
    alerts = json.loads(
        subprocess.run(
            [*COMPOSE, "exec", "-T", "alertmanager", "amtool", "alert", "query", "user=outage",
             "--output=json", "--alertmanager.url=http://127.0.0.1:9093"],
            check=True, cwd=ROOT, env=COMPOSE_ENV, capture_output=True, text=True,
        ).stdout
    )  # fmt: skip
    [alert] = alerts
    starts = _parse_go_time(alert["startsAt"])
    ends = _parse_go_time(alert["endsAt"])
    assert ends - starts == timedelta(minutes=5)
    assert starts.timestamp() >= restarted - 2


def test_old_lines_and_allowed_ports_never_alert(stack: Path):
    # Runs last (pytest keeps file order): by now every other alert has had
    # time to arrive, and neither of these may have.
    all_text = "\n".join(text_of(m) for m in messages())
    assert "oldsession" not in all_text
    assert ":22" not in all_text
    assert "5432" not in all_text


def test_nothing_else_alerted(stack: Path):
    """No alert fired that no test caused (a startup false alarm, for example)."""
    expected = {
        "SSHLogin", "SudoCommand", "SudoAuthFailure", "SSHFailedLoginBurst",
        "SSHFailedLoginFlood", "NewListeningPort", "DeliveryTest", "AppDown",
    }  # fmt: skip
    names = {text_of(m).split("<b>", 1)[1].split("</b>", 1)[0] for m in messages()}
    assert names - expected == set()
