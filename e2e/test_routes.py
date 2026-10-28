"""The committed Alertmanager config is valid, and routes each kind of alert
to the right receiver. Uses `amtool` from the pinned image; needs Docker."""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parent.parent
COMPOSE = (ROOT / "deploy" / "compose.yaml").read_text()
_match = re.search(r"image: (prom/alertmanager:\S+)", COMPOSE)
assert _match is not None
IMAGE: str = _match.group(1)
CONFIG = "/etc/alertmanager/alertmanager.yml"


def amtool(tmp_path: Path, *args: str) -> str:
    secrets = tmp_path / "secrets"
    secrets.mkdir(exist_ok=True)
    (secrets / "telegram_bot_token").write_text("dummy\n")
    (secrets / "telegram_chat_id").write_text("1\n")
    alertmanager = ROOT / "deploy" / "alertmanager"
    result = subprocess.run(
        [
            "docker", "run", "--rm", "--entrypoint", "amtool",
            "-v", f"{alertmanager / 'alertmanager.yml'}:{CONFIG}:ro",
            "-v", f"{alertmanager / 'templates'}:/etc/alertmanager/templates:ro",
            "-v", f"{secrets}:/etc/alertmanager/secrets:ro",
            IMAGE, *args,
        ],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def test_config_is_valid(tmp_path: Path):
    assert "SUCCESS" in amtool(tmp_path, "check-config", CONFIG)


@pytest.mark.parametrize(
    ("labels", "receiver"),
    [
        # Events: one-shot, never "resolved".
        ("alertname=SSHLogin severity=page event_id=a", "telegram-page-event"),
        ("alertname=SSHLogin severity=ticket event_id=a", "telegram-ticket-event"),
        ("alertname=SSHFailedLoginBurst severity=ticket event_id=b", "telegram-ticket-event"),
        # States: stay firing while true, then resolve.
        ("alertname=NewListeningPort severity=page", "telegram-page"),
        ("alertname=SomethingLater severity=ticket", "telegram-ticket"),
        # Anything unlabelled still reaches Arthur, loudly.
        ("alertname=Unknown", "telegram-page"),
    ],
)
def test_routing(tmp_path: Path, labels: str, receiver: str):
    out = amtool(tmp_path, "config", "routes", "test", f"--config.file={CONFIG}", *labels.split())
    assert out == receiver
