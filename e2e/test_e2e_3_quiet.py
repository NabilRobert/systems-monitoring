"""End to end: what must *not* have alerted. Runs after the other e2e files
(pytest orders them by name), so every caused alert has had time to arrive."""

import re
from pathlib import Path

import pytest

from e2e.stack import messages, text_of

pytestmark = pytest.mark.e2e


def test_old_lines_and_allowed_ports_never_alert(stack: Path):
    all_text = "\n".join(text_of(m) for m in messages())
    assert "oldsession" not in all_text
    assert ":22" not in all_text
    assert "5432" not in all_text


def test_nothing_else_alerted(stack: Path):
    """No alert fired that no test caused (a startup false alarm, for example)."""
    expected = {
        "SSHLogin", "SudoCommand", "SudoAuthFailure", "SSHFailedLoginFlood",
        "NewListeningPort", "DeliveryTest", "AppDown",
    }  # fmt: skip
    # The headline is "<status> · <b>Alert Name</b>": the name with spaces
    # added between words, so they are taken out again here.
    names: set[str] = set()
    for message in messages():
        headline = re.search(r"· <b>(.+?)</b>", text_of(message))
        assert headline is not None, text_of(message)
        names.add(headline.group(1).replace(" ", ""))
    assert names - expected == set()
