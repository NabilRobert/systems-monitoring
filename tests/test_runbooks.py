"""Every alert links a runbook that exists, and the runbook index lists it.

Reads the alert names and runbook links straight out of the Vector rules,
so a new rule without a runbook fails here."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RULES = (ROOT / "deploy" / "vector" / "vector.yaml").read_text()
RUNBOOKS = ROOT / "docs" / "runbooks"

ALERT_NAMES = set(re.findall(r'alertname"?\s*[:=]\s*"(\w+)"', RULES))
RUNBOOK_SLUGS = set(re.findall(r'runbook = "([a-z-]+)"', RULES)) | set(
    re.findall(r'/([a-z-]+)\.md"', RULES)
)
# Sent by hand with amtool to check delivery (docs/runbooks/test-alert.md).
MANUAL_ALERTS = {"DeliveryTest"}


def test_the_rules_define_all_six_alerts():
    assert ALERT_NAMES == {
        "SSHLogin",
        "SudoCommand",
        "SudoAuthFailure",
        "SSHFailedLoginBurst",
        "SSHFailedLoginFlood",
        "NewListeningPort",
    }


def test_every_runbook_an_alert_links_exists():
    missing = [slug for slug in RUNBOOK_SLUGS if not (RUNBOOKS / f"{slug}.md").is_file()]
    assert RUNBOOK_SLUGS, "found no runbook links in vector.yaml"
    assert missing == []


def test_the_runbook_index_lists_every_alert():
    index = (RUNBOOKS / "README.md").read_text()
    unlisted = [name for name in ALERT_NAMES | MANUAL_ALERTS if f"`{name}`" not in index]
    assert unlisted == []
