"""Git through its porcelain: repository root, tracked files, status, attributes, changed lines, staged paths,
stored bytes and one file's unstaged diff, all read-only, and one write, a patch applied to the index.

Every call passes -c core.quotepath=false, so a non-ASCII path comes back as UTF-8, uses -z wherever it
parses paths, and has a timeout. A call that fails raises GitError, so a caller never mistakes a failure for
an answer. A path that is not UTF-8 decodes with its bytes kept as surrogates, which the file system takes
back on macOS, so one odd file name never stops a check.
"""
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ioguard.lib import proc

PATHS = "surrogateescape"


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
    fields = raw.decode("utf-8", PATHS).split("\0")
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
    fields = raw.decode("utf-8", PATHS).split("\0")
    return {fields[at + 1]: fields[at + 2] for at in range(0, len(fields) - 2, 3)}


def reason(result: proc.RunResult) -> str:
    """Why a git call failed, in git's words where it gave any."""
    return result.start_error or ("timed out" if result.timed_out else
                                  result.stderr.decode("utf-8", "replace").strip())


class Git:
    """The GitPort io-guard uses in a live session."""

    def __init__(self, timeout_s: float = 10.0, deadline: float | None = None) -> None:
        self.timeout_s = timeout_s
        self.deadline = deadline         # a time.monotonic() no call runs past, None for none

    def within(self, seconds: float) -> "Git":
        """This git with every call ending by seconds from now, so a hook's git calls share its budget."""
        return Git(self.timeout_s, time.monotonic() + seconds)

    def time_left(self, args: tuple[str, ...]) -> float:
        """The seconds a call may take, GitError when the deadline has passed."""
        if self.deadline is None:
            return self.timeout_s
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise GitError(f"git {' '.join(args)} did not run, because the hook's time budget had run out.")
        return min(self.timeout_s, left)

    def run(self, cwd: Path, *args: str) -> proc.RunResult:
        return proc.run(["git", "-c", "core.quotepath=false", *args], cwd=cwd, timeout_s=self.time_left(args))

    def checked(self, cwd: Path, *args: str) -> bytes:
        result = self.run(cwd, *args)
        if not result.ok:
            raise GitError(f"git {' '.join(args)} in {cwd} failed: {reason(result)}")
        return result.stdout

    @staticmethod
    def folder(path: Path) -> Path:
        return path if path.is_dir() else path.parent

    def root(self, path: Path) -> Path | None:
        """The repository root holding path, or None when path is outside every repository."""
        result = self.run(self.folder(path), "rev-parse", "--show-toplevel")
        if result.ok:
            return Path(result.stdout.decode("utf-8", PATHS).strip())
        if b"not a git repository" in result.stderr:
            return None
        raise GitError(f"git rev-parse in {path} failed: {reason(result)}")

    def is_tracked(self, path: Path) -> bool:
        result = self.run(path.parent, "ls-files", "--error-unmatch", "--", path.name)
        if result.exit_code is None:
            raise GitError(f"git ls-files for {path} failed: {reason(result)}")
        return result.ok

    def status(self, root: Path) -> GitStatus:
        return parse_status(self.checked(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"))

    def ls_files(self, root: Path) -> tuple[Path, ...]:
        names = self.checked(root, "ls-files", "-z").decode("utf-8", PATHS).split("\0")
        return tuple(root / name for name in names if name)

    def changed_ranges(self, path: Path) -> tuple[LineRange, ...] | None:
        """The lines of path that differ from its last commit, staged or not, read as text whatever its
        attributes say. None when git holds no commit of it: an untracked file, a file outside every
        repository, or a repository with no commit yet."""
        if not self.is_tracked(path):
            return None
        result = self.run(path.parent, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
                          "--text", "HEAD", "--", path.name)
        if result.ok:
            return parse_ranges(result.stdout)
        if result.exit_code is not None and not self.run(path.parent, "rev-parse", "--verify", "HEAD").ok:
            return None
        raise GitError(f"git diff HEAD for {path} failed: {reason(result)}")

    def attributes(self, path: Path) -> Mapping[str, str]:
        return parse_attributes(self.checked(path.parent, "check-attr", "-a", "-z", "--", path.name))

    def staged(self, root: Path) -> tuple[str, ...]:
        """The paths the next commit adds, changes or renames to, from root, with forward slashes."""
        raw = self.checked(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
        return tuple(name for name in raw.decode("utf-8", PATHS).split("\0") if name)

    def unstaged(self, path: Path) -> bytes:
        """path's changes the index does not hold yet, as git diff -U0 bytes, with no textconv, no external
        diff and no colour. Empty when there are none."""
        return self.checked(path.parent, "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", "--",
                            path.name)

    def stage_patch(self, root: Path, patch: bytes) -> None:
        """Apply patch to the index only, as git apply --cached, which a -U0 patch needs --unidiff-zero for.
        GitError carries git's own reason when it refuses."""
        result = proc.run(["git", "-c", "core.quotepath=false", "apply", "--cached", "--unidiff-zero",
                           "--recount", "-"], cwd=root, timeout_s=self.time_left(("apply",)), stdin=patch)
        if not result.ok:
            raise GitError(f"git apply --cached in {root} failed: {reason(result)}")

    def blob(self, root: Path, spec: str) -> bytes | None:
        """The bytes git stores for spec, such as HEAD:src/a.py, or :src/a.py for the staged file. None when
        git holds nothing there, such as a file new to this commit."""
        result = self.run(root, "cat-file", "blob", spec)
        if result.exit_code is None:
            raise GitError(f"git cat-file blob {spec} failed: {reason(result)}")
        return result.stdout if result.ok else None
