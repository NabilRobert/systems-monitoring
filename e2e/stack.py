"""Shared helpers for the end-to-end tests: the stack, its inputs, and what arrived.

The tests run the production compose file with e2e/compose.override.yaml on
top, so the images, hardening, memory caps and routing tree are the real
ones. Inputs are a synthetic auth log and socket table (in e2e/out/), and
what arrives is read from the Telegram stand-in's record. Addresses are
documentation ranges (RFC 5737).
"""

import json
import os
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "e2e" / "out"
FIXTURES = ROOT / "tests" / "fixtures"
# Compose reads HOST_LABEL for vmalert's host label, as from deploy/.env on
# the server.
COMPOSE_ENV = {**os.environ, "HOST_LABEL": "e2e-host"}
COMPOSE_FILES = [
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


def compose(*args: str, check: bool = True) -> str:
    """Run `docker compose` on the test stack; returns its standard output."""
    result = subprocess.run(
        ["docker", "compose", *COMPOSE_FILES, *args],
        check=False, cwd=ROOT, env=COMPOSE_ENV, capture_output=True, text=True,
    )  # fmt: skip
    if check and result.returncode != 0:
        raise AssertionError(f"docker compose {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def line(message: str, program: str = "sshd[812]") -> str:
    ts = datetime.now(WIB).isoformat(timespec="microseconds")
    return f"{ts} e2e-host {program}: {message}\n"


def append(*lines: str) -> float:
    """Append to the synthetic auth log; returns when it was written."""
    with (OUT / "log" / "auth.log").open("a") as f:
        f.writelines(lines)
    return time.time()


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


def check(message: dict[str, object], written_at: float, silent: bool) -> None:
    """The message went to the right chat, as HTML, buzzing or not, within 60 s."""
    body = message["body"]
    assert isinstance(body, dict)
    assert str(body["chat_id"]) == str(CHAT_ID)  # pyright: ignore[reportUnknownArgumentType]
    assert body["parse_mode"] == "HTML"
    assert bool(body.get("disable_notification", False)) is silent  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    latency = float(message["received_at"]) - written_at  # pyright: ignore[reportArgumentType]
    record_latency(text_of(message).splitlines()[0], latency)
    assert latency < MAX_LATENCY, f"took {latency:.1f} s"


def record_latency(what: str, seconds: float) -> None:
    """Kept in e2e/out/latency.txt, for the README's measured numbers."""
    with (OUT / "latency.txt").open("a") as f:
        f.write(f"{what}\t{seconds:.1f}\n")


def query_metrics(promql: str) -> list[dict[str, object]]:
    """An instant query to VictoriaMetrics, from inside the compose network."""
    url = "http://victoriametrics:8428/api/v1/query?query=" + urllib.parse.quote(promql)
    result = json.loads(compose("exec", "-T", "vector", "wget", "-q", "-O", "-", url))["data"][
        "result"
    ]
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


def parse_go_time(text: str) -> datetime:
    """Go prints up to 9 fractional digits; Python's parser takes at most 6."""
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", text))
