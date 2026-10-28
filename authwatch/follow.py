"""Follow a log file the way `tail -F` does, across rotation."""

import os
from pathlib import Path
from typing import BinaryIO


class Follower:
    """Returns the complete lines added to a file since the last poll.

    - Starts at the end of the file, so old lines never alert, unless
      `from_start` is set (used by tests).
    - Rotation (the path now names a new file): the rest of the old file is
      read, then the new file from its start.
    - Truncation (the file got shorter): reads again from the start.
    - A missing file is waited for, not an error.
    - A line without its newline yet is held until it is complete.
    """

    def __init__(self, path: Path, from_start: bool = False) -> None:
        self._path = path
        self._file: BinaryIO | None = None
        self._inode: int | None = None
        self._partial = b""
        self._open(at_end=not from_start)

    def _open(self, at_end: bool) -> None:
        try:
            handle = self._path.open("rb")
        except FileNotFoundError:
            self._file = None
            self._inode = None
            return
        self._file = handle
        self._inode = os.fstat(handle.fileno()).st_ino
        if at_end:
            handle.seek(0, os.SEEK_END)

    def poll(self) -> list[str]:
        if self._file is None:
            self._open(at_end=False)
            return self._read() if self._file is not None else []
        try:
            current = self._path.stat()
        except FileNotFoundError:
            # Rotated away and not yet recreated: finish the old file.
            return self._read()
        if current.st_ino != self._inode:
            lines = self._read()
            self._file.close()
            self._partial = b""
            self._open(at_end=False)
            return lines + self._read()
        if current.st_size < self._file.tell():
            self._file.seek(0)
            self._partial = b""
        return self._read()

    def _read(self) -> list[str]:
        if self._file is None:
            return []
        data = self._partial + self._file.read()
        *complete, self._partial = data.split(b"\n")
        return [line.decode("utf-8", errors="replace") for line in complete]

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
