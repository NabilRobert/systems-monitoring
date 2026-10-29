"""The one stack all the end-to-end tests share (started once per session)."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from e2e.stack import CHAT_ID, OUT, ROOT, TCP_BASE, compose, line, messages, write_atomic


def _prepare_inputs() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for sub in ("log", "net", "messages", "secrets"):
        (OUT / sub).mkdir(parents=True)
    (OUT / "messages").chmod(0o777)
    (OUT / "secrets" / "telegram_bot_token").write_text("123456:dummy-token-for-e2e\n")
    (OUT / "secrets" / "telegram_chat_id").write_text(f"{CHAT_ID}\n")
    # The production Alertmanager config, with only the Telegram address
    # pointed at the stand-in.
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


@pytest.fixture(scope="session")
def stack() -> Iterator[Path]:
    _prepare_inputs()
    compose("up", "-d", "--build", "--wait")
    try:
        yield OUT
    finally:
        if not messages():
            print(compose("logs", "--no-color", check=False))
        compose("down", "-v", "--remove-orphans")
