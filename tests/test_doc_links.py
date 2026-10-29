"""Every relative link in the Markdown docs points at a file that exists,
so moving a doc without fixing its links fails here."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
# [text](target) where target isn't a web address or an in-page anchor.
RELATIVE_LINK = re.compile(r"\[[^\]]*\]\((?!https?://|#|mailto:)([^)\s]+)\)")


def markdown_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.md"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()  # fmt: skip
    return [ROOT / name for name in listed]


def broken_links(path: Path) -> list[str]:
    broken: list[str] = []
    in_code = False
    for number, line in enumerate(path.read_text().splitlines(), start=1):
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for target in RELATIVE_LINK.findall(line):
            file_part = target.split("#", 1)[0]
            if not (path.parent / file_part).exists():
                broken.append(f"{path.relative_to(ROOT)}:{number}: {target}")
    return broken


def test_the_docs_are_found():
    names = {path.relative_to(ROOT).as_posix() for path in markdown_files()}
    assert {"README.md", "docs/guide.md", "docs/adr/README.md"} <= names


def test_every_relative_link_in_the_docs_resolves():
    broken = [link for path in markdown_files() for link in broken_links(path)]
    assert broken == []
