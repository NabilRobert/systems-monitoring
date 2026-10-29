"""Runs the alert-rule unit tests in deploy/vmalert/tests/ with `vmalert-tool
unittest`, in the image matching the pinned vmalert, so they fail CI like
any other test. Needs Docker; takes about 90 s (one test covers 3 days)."""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parent.parent
VMALERT_DIR = ROOT / "deploy" / "vmalert"
_version = re.search(
    r"image: victoriametrics/vmalert:(v[\d.]+)@", (ROOT / "deploy" / "compose.yaml").read_text()
)
assert _version is not None, "deploy/compose.yaml has no pinned victoriametrics/vmalert image"
# vmalert-tool is released with vmalert under the same version; pinned by
# digest like every other image, and checked to match vmalert's version.
TOOL_IMAGE = (
    "victoriametrics/vmalert-tool:v1.154.0"
    "@sha256:f7625a4441ab53a08c7aed5464149ce962fe00f91b5da75c911df56c09e3c2e7"
)
assert f":{_version.group(1)}@" in TOOL_IMAGE, "update TOOL_IMAGE to vmalert's version"


def test_every_alert_rule_test_passes():
    result = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{VMALERT_DIR}:/etc/vmalert:ro",
            "-w", "/etc/vmalert/tests",
            TOOL_IMAGE, "unittest", "--disableAlertgroupLabel",
            "--files=/etc/vmalert/tests/*_test.yml",
        ],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    # One "Unit Testing: <file>" line per test file: both must have run.
    assert output.count("Unit Testing:") == 2, output
    assert "SUCCESS" in output, output
