"""Every alert links a runbook that exists, and the runbook index lists it.

Reads the alert names and runbook links straight out of the Vector rules
and the vmalert rules, so a new rule without a runbook fails here."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
RULES = (ROOT / "deploy" / "vector" / "vector.yaml").read_text()
METRIC_RULES = (ROOT / "deploy" / "vmalert" / "rules.yml").read_text()
RUNBOOKS = ROOT / "docs" / "runbooks"

ALERT_NAMES = set(re.findall(r'alertname"?\s*[:=]\s*"(\w+)"', RULES))
METRIC_ALERT_NAMES = set(re.findall(r"^\s+- alert: (\w+)$", METRIC_RULES, re.MULTILINE))
RUNBOOK_SLUGS = (
    set(re.findall(r'runbook = "([a-z-]+)"', RULES))
    | set(re.findall(r'/([a-z-]+)\.md"', RULES))
    | set(re.findall(r"runbooks/([a-z-]+)\.md$", METRIC_RULES, re.MULTILINE))
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


def test_every_metric_alert_links_a_runbook():
    alerts = METRIC_RULES.split("- alert: ")[1:]
    assert len(alerts) == len(METRIC_ALERT_NAMES) == 12
    unlinked = [a.split()[0] for a in alerts if "runbook_url: https://" not in a]
    assert unlinked == []


def test_every_runbook_an_alert_links_exists():
    missing = [slug for slug in RUNBOOK_SLUGS if not (RUNBOOKS / f"{slug}.md").is_file()]
    assert RUNBOOK_SLUGS, "found no runbook links in vector.yaml"
    assert missing == []


def test_the_runbook_index_lists_every_alert():
    index = (RUNBOOKS / "README.md").read_text()
    every_alert = ALERT_NAMES | METRIC_ALERT_NAMES | MANUAL_ALERTS
    unlisted = [name for name in every_alert if f"`{name}`" not in index]
    assert unlisted == []
