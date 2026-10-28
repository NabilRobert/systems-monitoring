"""End to end in Docker: log line → detector → Alertmanager → Telegram stand-in.

Runs the production compose file with e2e/compose.override.yaml on top, so
the images, hardening, memory caps and routing tree are the real ones.
Needs Docker. Run with `uv run pytest -m e2e e2e/` (about 3 minutes).
Addresses are documentation ranges (RFC 5737).
"""

import json
import shlex
import shutil
import subprocess
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parent.parent
OUT = ROOT / "e2e" / "out"
FIXTURES = ROOT / "tests" / "fixtures"
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
    subprocess.run([*COMPOSE, "up", "-d", "--build", "--wait"], check=True, cwd=ROOT)
    try:
        yield OUT
    finally:
        if not messages():
            subprocess.run([*COMPOSE, "logs", "--no-color"], check=False, cwd=ROOT)
        subprocess.run([*COMPOSE, "down", "-v", "--remove-orphans"], check=True, cwd=ROOT)


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
    )
    check(wait_for("Test alert: delivery works"), sent_at, silent=False)


def test_old_lines_and_allowed_ports_never_alert(stack: Path):
    # Runs last (pytest keeps file order): by now every other alert has had
    # time to arrive, and neither of these may have.
    all_text = "\n".join(text_of(m) for m in messages())
    assert "oldsession" not in all_text
    assert ":22" not in all_text
    assert "5432" not in all_text
