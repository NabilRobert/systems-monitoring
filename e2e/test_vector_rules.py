"""Runs the rule unit tests in deploy/vector/tests/ with `vector test`, in the
pinned Vector image, so they fail CI like any other test. Needs Docker."""

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).parent.parent
VECTOR_DIR = ROOT / "deploy" / "vector"
_image = re.search(r"image: (timberio/vector:\S+)", (ROOT / "deploy" / "compose.yaml").read_text())
assert _image is not None, "deploy/compose.yaml has no timberio/vector image line"
VECTOR_IMAGE: str = _image.group(1)

# The settings the tests in deploy/vector/tests/rules.yaml are written for.
TEST_SETTINGS = {
    "HOST_LABEL": "test-host",
    "SECURITY_ALLOWED_PORTS": "22",
    "SECURITY_KNOWN_NETWORKS": "192.0.2.0/24",
    "SECURITY_RUNBOOK_BASE": "https://example.org/runbooks",
}


def test_every_vector_rule_test_passes():
    env_args = [arg for name, value in TEST_SETTINGS.items() for arg in ("-e", f"{name}={value}")]
    result = subprocess.run(
        [
            "docker", "run", "--rm", *env_args,
            "-v", f"{VECTOR_DIR}:/etc/vector:ro",
            VECTOR_IMAGE, "test", "/etc/vector/vector.yaml", "/etc/vector/tests/rules.yaml",
        ],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    # One line per test, "test <name> ... passed" (names may contain "failed").
    results = [line for line in output.splitlines() if line.startswith("test ")]
    assert len(results) >= 28, output
    assert all(line.endswith("... passed") for line in results), output
