"""The ports a check reads the machine through: git, the file system and the clock, and the live ones.

A check never touches the disk, git or the time itself, so a test hands it lib.fakes' in-memory ports.
"""
import errno
import logging
import os
import stat as stat_module
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ioguard.lib import bytesio, locks, paths
from ioguard.lib.git import GitStatus, LineRange
from ioguard.lib.locks import Process
from ioguard.lib.platform import detect

log = logging.getLogger("ioguard.lib")

NO_SUCH_PATH = {errno.ENOENT, errno.ENOTDIR, errno.EINVAL, errno.ENAMETOOLONG}   # a stat no file can answer
COUNT_BLOCK = 1024 * 1024       # the bytes newlines reads at a time, so a large log is never read whole


@dataclass(frozen=True)
class FileStat:
    size: int
    mtime_ns: int
    readonly: bool


class GitPort(Protocol):
    def within(self, seconds: float) -> GitPort: ...            # every call ends by seconds from now
    def root(self, path: Path) -> Path | None: ...
    def is_tracked(self, path: Path) -> bool: ...
    def status(self, root: Path) -> GitStatus: ...
    def ls_files(self, root: Path) -> tuple[Path, ...]: ...
    def changed_ranges(self, path: Path) -> tuple[LineRange, ...] | None: ...   # since HEAD, None untracked
    def attributes(self, path: Path) -> Mapping[str, str]: ...
    def staged(self, root: Path) -> tuple[str, ...]: ...
    def blob(self, root: Path, spec: str) -> bytes | None: ...
    def unstaged(self, path: Path) -> bytes: ...                  # git diff -U0 of path against the index
    def stage_patch(self, root: Path, patch: bytes) -> None: ...  # git apply --cached, GitError on refusal


class FsPort(Protocol):
    def read_bytes(self, path: Path, limit: int | None = None) -> bytes: ...
    def read_tail(self, path: Path, limit: int) -> bytes: ...  # the last whole lines within limit bytes
    def read_from(self, path: Path, offset: int, limit: int) -> bytes: ...   # limit bytes from offset on
    def write_atomic(self, path: Path, data: bytes) -> bytesio.WriteReport: ...
    def append(self, path: Path, data: bytes) -> None: ...     # at the end, for a file others append to
    def stat(self, path: Path) -> FileStat | None: ...
    def exists(self, path: Path) -> bool: ...
    def is_dir(self, path: Path) -> bool: ...
    def holders(self, path: Path) -> tuple[Process, ...]: ...  # OSError when the platform cannot answer
    def make_folders(self, path: Path) -> None: ...
    def list_dir(self, path: Path) -> tuple[Path, ...]: ...    # the files in a folder, sorted, () when none
    def link_target(self, path: Path) -> Path | None: ...      # where a path through a link really is
    def find_named(self, root: Path, name: str, limit: int) -> tuple[Path, ...]: ...
                                                               # files named name under root, in limit entries
    def files_under(self, root: Path, limit: int,
                    keep: Callable[[Path], bool] | None = None) -> tuple[Path, ...]: ...
                                                               # sorted, outside .git, at most limit + 1 kept


class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


class LiveFs:
    """The file system, through lib.bytesio."""

    def read_bytes(self, path: Path, limit: int | None = None) -> bytes:
        return bytesio.read_bytes(path, limit)

    def read_tail(self, path: Path, limit: int) -> bytes:
        return bytesio.read_tail(path, limit)

    def read_from(self, path: Path, offset: int, limit: int) -> bytes:
        return bytesio.read_from(path, offset, limit)

    def write_atomic(self, path: Path, data: bytes) -> bytesio.WriteReport:
        return bytesio.write_atomic(path, data)

    def append(self, path: Path, data: bytes) -> None:
        bytesio.append(path, data)

    def stat(self, path: Path) -> FileStat | None:
        """path's size, time and read-only flag, or None when no file can be there: missing, through a
        file, or a name the system rejects, such as one holding ? on Windows or one too long."""
        try:
            found = os.stat(path)
        except OSError as error:
            if error.errno not in NO_SUCH_PATH:
                raise
            log.debug("io-guard found no file at %s: %s", path, error)
            return None
        return FileStat(found.st_size, found.st_mtime_ns, not found.st_mode & stat_module.S_IWRITE)

    def exists(self, path: Path) -> bool:
        return path.exists()

    def is_dir(self, path: Path) -> bool:
        return path.is_dir()

    def holders(self, path: Path) -> tuple[Process, ...]:
        return locks.holders(path, detect())

    def make_folders(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def list_dir(self, path: Path) -> tuple[Path, ...]:
        try:
            with os.scandir(path) as entries:
                return tuple(sorted(Path(entry.path) for entry in entries if entry.is_file()))
        except OSError:
            return ()

    def link_target(self, path: Path) -> Path | None:
        return paths.link_target(path)

    def find_named(self, root: Path, name: str, limit: int) -> tuple[Path, ...]:
        """Files named name, without case, under root, from the first limit entries a walk meets."""
        wanted, found, seen = name.casefold(), [], 0
        for folder, folders, files in os.walk(root):
            folders[:] = [child for child in folders if not child.startswith(".")]
            seen += len(files) + len(folders)
            found += [Path(folder) / file for file in files if file.casefold() == wanted]
            if seen >= limit:
                break
        return tuple(found)

    def files_under(self, root: Path, limit: int,
                    keep: Callable[[Path], bool] | None = None) -> tuple[Path, ...]:
        """Every file under root that keep takes, or every file, outside .git folders, sorted. A walk stops
        once it holds more than limit, so a caller sees that the folder holds more."""
        found: list[Path] = []
        for folder, folders, files in os.walk(root):
            folders[:] = sorted(child for child in folders if child != ".git")
            walked = [Path(folder) / file for file in files]
            found += walked if keep is None else [path for path in walked if keep(path)]
            if len(found) > limit:
                break
        return tuple(sorted(found)[:limit + 1])


def newlines(fs: FsPort, path: Path, end: int) -> int:
    """The line breaks in path's first end bytes, read in blocks. OSError when the file cannot be read."""
    count = at = 0
    while at < end:
        block = fs.read_from(path, at, min(COUNT_BLOCK, end - at))
        if not block:
            break
        count, at = count + block.count(b"\n"), at + len(block)
    return count


def read_or_none(fs: FsPort, path: Path, limit: int | None = None) -> bytes | None:
    """path's bytes, at most limit of them, or None when it is gone or cannot be read."""
    try:
        return fs.read_bytes(path, limit)
    except OSError:
        return None
