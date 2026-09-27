"""Git through its porcelain, read-only: repository root, tracked files, status, attributes, changed lines,
staged paths and stored bytes.

Every call passes -c core.quotepath=false, so a non-ASCII path comes back as UTF-8, uses -z wherever it
parses paths, and has a timeout. A call that fails raises GitError, so a caller never mistakes a failure for
an answer.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ioguard.lib import proc


class GitError(Exception):
    pass


@dataclass(frozen=True)
class StatusEntry:
    path: str                    # relative to the repository root, with forward slashes
    index: str                   # the X of git's XY status code
    worktree: str                # the Y
    original: str | None = None  # the old path of a rename or copy

    @property
    def untracked(self) -> bool:
        return self.index == "?"


@dataclass(frozen=True)
class GitStatus:
    entries: tuple[StatusEntry, ...]


@dataclass(frozen=True)
class LineRange:
    start: int                   # first line in the new file, counting from 1
    count: int                   # 0 for a pure deletion before line start


def parse_status(raw: bytes) -> GitStatus:
    """Parse git status --porcelain=v1 -z, where a rename carries its old path as the next field."""
    fields = raw.decode("utf-8").split("\0")
    entries, at = [], 0
    while at < len(fields) and fields[at]:
        field = fields[at]
        index, worktree, path = field[0], field[1], field[3:]
        original = None
        if index in "RC":
            at += 1
            original = fields[at]
        entries.append(StatusEntry(path, index, worktree, original))
        at += 1
    return GitStatus(tuple(entries))


HUNK = re.compile(rb"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def parse_ranges(raw: bytes) -> tuple[LineRange, ...]:
    """The line ranges of the new file that git diff -U0 reports as changed."""
    return tuple(LineRange(int(start), 1 if count == b"" else int(count))
                 for start, count in HUNK.findall(raw))


def parse_attributes(raw: bytes) -> dict[str, str]:
    """Parse git check-attr -a -z: path, attribute and value, each ended by NUL."""
    fields = raw.decode("utf-8").split("\0")
    return {fields[at + 1]: fields[at + 2] for at in range(0, len(fields) - 2, 3)}


class Git:
    """The GitPort io-guard uses in a live session."""

    def __init__(self, timeout_s: float = 10.0) -> None:
        self.timeout_s = timeout_s

    def run(self, cwd: Path, *args: str) -> proc.RunResult:
        return proc.run(["git", "-c", "core.quotepath=false", *args], cwd=cwd, timeout_s=self.timeout_s)

    def checked(self, cwd: Path, *args: str) -> bytes:
        result = self.run(cwd, *args)
        if not result.ok:
            reason = result.start_error or ("timed out" if result.timed_out else
                                            result.stderr.decode("utf-8", "replace").strip())
            raise GitError(f"git {' '.join(args)} in {cwd} failed: {reason}")
        return result.stdout

    @staticmethod
    def folder(path: Path) -> Path:
        return path if path.is_dir() else path.parent

    def root(self, path: Path) -> Path | None:
        """The repository root holding path, or None when path is outside every repository."""
        result = self.run(self.folder(path), "rev-parse", "--show-toplevel")
        if result.ok:
            return Path(result.stdout.decode("utf-8").strip())
        if b"not a git repository" in result.stderr:
            return None
        raise GitError(f"git rev-parse in {path} failed: "
                       f"{result.start_error or result.stderr.decode('utf-8', 'replace').strip()}")

    def is_tracked(self, path: Path) -> bool:
        result = self.run(path.parent, "ls-files", "--error-unmatch", "--", path.name)
        if result.start_error or result.timed_out:
            raise GitError(f"git ls-files for {path} failed: {result.start_error or 'timed out'}")
        return result.ok

    def status(self, root: Path) -> GitStatus:
        return parse_status(self.checked(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"))

    def ls_files(self, root: Path) -> tuple[Path, ...]:
        names = self.checked(root, "ls-files", "-z").decode("utf-8").split("\0")
        return tuple(root / name for name in names if name)

    def changed_ranges(self, path: Path) -> tuple[LineRange, ...]:
        raw = self.checked(path.parent, "diff", "-U0", "--no-color", "--no-ext-diff", "--", path.name)
        return parse_ranges(raw)

    def attributes(self, path: Path) -> Mapping[str, str]:
        return parse_attributes(self.checked(path.parent, "check-attr", "-a", "-z", "--", path.name))

    def staged(self, root: Path) -> tuple[str, ...]:
        """The paths the next commit adds, changes or renames to, from root, with forward slashes."""
        raw = self.checked(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
        return tuple(name for name in raw.decode("utf-8").split("\0") if name)

    def blob(self, root: Path, spec: str) -> bytes | None:
        """The bytes git stores for spec, such as HEAD:src/a.py, or :src/a.py for the staged file. None when
        git holds nothing there, such as a file new to this commit."""
        result = self.run(root, "cat-file", "blob", spec)
        if result.start_error or result.timed_out:
            raise GitError(f"git cat-file blob {spec} failed: {result.start_error or 'timed out'}")
        return result.stdout if result.ok else None
