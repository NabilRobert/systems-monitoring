"""Following the log across rotation, truncation and partial lines."""

from pathlib import Path

from authwatch.follow import Follower


def append(path: Path, text: str) -> None:
    with path.open("a") as f:
        f.write(text)


def test_starts_at_the_end(tmp_path: Path):
    log = tmp_path / "auth.log"
    log.write_text("old line\n")
    follower = Follower(log)
    assert follower.poll() == []
    append(log, "new line\n")
    assert follower.poll() == ["new line"]


def test_from_start_reads_existing_lines(tmp_path: Path):
    log = tmp_path / "auth.log"
    log.write_text("a\nb\n")
    assert Follower(log, from_start=True).poll() == ["a", "b"]


def test_partial_line_waits_for_its_newline(tmp_path: Path):
    log = tmp_path / "auth.log"
    log.write_text("")
    follower = Follower(log)
    append(log, "half")
    assert follower.poll() == []
    append(log, " done\nnext")
    assert follower.poll() == ["half done"]


def test_rotation_by_rename_reads_the_old_tail_then_the_new_file(tmp_path: Path):
    log = tmp_path / "auth.log"
    log.write_text("")
    follower = Follower(log)
    append(log, "before\n")
    append(log, "last in old file\n")
    log.rename(tmp_path / "auth.log.1")
    log.write_text("first in new file\n")
    assert follower.poll() == ["before", "last in old file", "first in new file"]
    append(log, "more\n")
    assert follower.poll() == ["more"]


def test_rotated_away_and_not_yet_recreated(tmp_path: Path):
    log = tmp_path / "auth.log"
    log.write_text("")
    follower = Follower(log)
    append(log, "tail\n")
    log.rename(tmp_path / "auth.log.1")
    assert follower.poll() == ["tail"]
    log.write_text("fresh\n")
    assert follower.poll() == ["fresh"]


def test_truncation_reads_from_the_start(tmp_path: Path):
    log = tmp_path / "auth.log"
    log.write_text("x" * 100 + "\n")
    follower = Follower(log)
    log.write_text("after copytruncate\n")
    assert follower.poll() == ["after copytruncate"]


def test_missing_file_is_waited_for(tmp_path: Path):
    log = tmp_path / "auth.log"
    follower = Follower(log)
    assert follower.poll() == []
    log.write_text("appeared\n")
    assert follower.poll() == ["appeared"]


def test_invalid_utf8_does_not_crash(tmp_path: Path):
    log = tmp_path / "auth.log"
    log.write_text("")
    follower = Follower(log)
    with log.open("ab") as f:
        f.write(b"bad \xff byte\n")
    assert follower.poll() == ["bad � byte"]
