"""The example probe targets are what the server's apps.yml is copied from:
each needs an `app` label (alerts, SLOs and silences use it) and an https
URL (so the probe also reports the certificate's expiry).

Read with regular expressions rather than a YAML library: the file is a
flat list, and the project has no runtime dependencies to add one to."""

import re
from pathlib import Path

EXAMPLE = Path(__file__).parent.parent / "deploy" / "targets" / "apps.yml.example"
TEXT = EXAMPLE.read_text()
URLS = re.findall(r'^- targets: \["([^"]+)"\]$', TEXT, re.MULTILINE)
APPS = re.findall(r"^    app: (\S+)$", TEXT, re.MULTILINE)


def test_every_target_has_one_app_label():
    assert URLS, "found no targets in apps.yml.example"
    assert len(APPS) == len(URLS)


def test_app_labels_are_unique():
    assert len(set(APPS)) == len(APPS)


def test_every_target_is_https_so_its_certificate_is_checked():
    plain = [url for url in URLS if not url.startswith("https://")]
    assert plain == []


def test_the_live_apps_are_all_probed():
    assert set(APPS) == {"mcp-backbone", "pitstop-demo", "framed"}
