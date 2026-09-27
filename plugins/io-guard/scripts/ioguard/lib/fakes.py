"""In-memory ports for tests: a file system of path to bytes, a git that answers what it was given, and a
clock that moves only when told. Context.fake builds them."""
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ioguard.lib.bytesio import WriteReport
from ioguard.lib.context import FileStat
from ioguard.lib.locks import Process
from ioguard.lib.git import GitStatus, LineRange

START = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, start: datetime = START) -> None:
        self.start = start
        self.elapsed_s = 0.0

    def advance(self, milliseconds: float) -> None:
        self.elapsed_s += milliseconds / 1000

    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.elapsed_s)

    def monotonic(self) -> float:
        return self.elapsed_s


class FakeFs:
    def __init__(self, files: Mapping[Path, bytes], readonly: frozenset[Path] = frozenset(),
                 holders: Mapping[Path, tuple[Process, ...]] | None = None,
                 links: Mapping[Path, Path] | None = None) -> None:
        self.files = dict(files)
        self.readonly = readonly
        self.held = dict(holders or {})
        self.links = dict(links or {})             # a linked folder to the folder it points at
        self.writes: list[Path] = []
        self.folders: set[Path] = set()

    def read_bytes(self, path: Path, limit: int | None = None) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        data = self.files[path]
        return data if limit is None else data[:limit]

    def write_atomic(self, path: Path, data: bytes) -> WriteReport:
        self.files[path] = data
        self.writes.append(path)
        return WriteReport(path=path, bytes_written=len(data), attempts=1)

    def stat(self, path: Path) -> FileStat | None:
        if path not in self.files:
            return None
        return FileStat(len(self.files[path]), self.writes.count(path), path in self.readonly)

    def exists(self, path: Path) -> bool:
        """A file given to the fake, or a folder that holds one or was made."""
        return path in self.files or path in self.folders or any(path in file.parents for file in self.files)

    def holders(self, path: Path) -> tuple[Process, ...]:
        return self.held.get(path, ())

    def make_folders(self, path: Path) -> None:
        self.folders.add(path)

    def list_dir(self, path: Path) -> tuple[Path, ...]:
        return tuple(sorted(file for file in self.files if file.parent == path))

    def read_tail(self, path: Path, limit: int) -> bytes:
        data = self.read_bytes(path)
        if len(data) <= limit:
            return data
        tail = data[-limit:]
        return tail[tail.find(b"\n") + 1:] if b"\n" in tail else b""

    def find_named(self, root: Path, name: str, limit: int) -> tuple[Path, ...]:
        return tuple(sorted(file for file in self.files
                            if file.name.casefold() == name.casefold() and root in file.parents))[:limit]

    def link_target(self, path: Path) -> Path | None:
        return next((target / path.relative_to(link) for link, target in self.links.items()
                     if path == link or link in path.parents), None)


class FakeGit:
    def __init__(self, root: Path | None = None, tracked: frozenset[Path] = frozenset(),
                 status: GitStatus = GitStatus(()),
                 ranges: Mapping[Path, tuple[LineRange, ...]] | None = None,
                 attributes: Mapping[Path, Mapping[str, str]] | None = None,
                 staged_paths: tuple[str, ...] = (), blobs: Mapping[str, bytes] | None = None,
                 other_roots: tuple[Path, ...] = ()) -> None:
        self.repo_root = root
        self.other_roots = other_roots             # more repositories, each the root of the paths under it
        self.staged_paths = staged_paths
        self.blobs = dict(blobs or {})             # by spec, such as HEAD:a.py or :a.py
        self.tracked = tracked
        self.current_status = status
        self.ranges = dict(ranges or {})
        self.attrs = dict(attributes or {})

    def root(self, path: Path) -> Path | None:
        return next((root for root in self.other_roots if root == path or root in path.parents),
                    self.repo_root)

    def is_tracked(self, path: Path) -> bool:
        return path in self.tracked

    def status(self, root: Path) -> GitStatus:
        return self.current_status

    def ls_files(self, root: Path) -> tuple[Path, ...]:
        return tuple(sorted(self.tracked))

    def changed_ranges(self, path: Path) -> tuple[LineRange, ...]:
        return self.ranges.get(path, ())

    def attributes(self, path: Path) -> Mapping[str, str]:
        return self.attrs.get(path, {})

    def staged(self, root: Path) -> tuple[str, ...]:
        return self.staged_paths

    def blob(self, root: Path, spec: str) -> bytes | None:
        return self.blobs.get(spec)
