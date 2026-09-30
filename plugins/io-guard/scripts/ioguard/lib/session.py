"""What io-guard learns during one session, and the snapshots a PreToolUse keeps for its PostToolUse.

One session's hooks and its io server are several processes. A warning's key goes into a file they all read,
so each warning goes out once per session whichever process meets it first.
"""
import json
import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ioguard.lib import bytesio, locks
from ioguard.lib.folders import session_file
from ioguard.lib.git import GitError
from ioguard.lib.ports import FileStat, GitPort
from ioguard.lib.profile import Profile

log = logging.getLogger("ioguard.lib")

SNAPSHOTS_KEPT = 16     # a call the user refuses leaves its snapshot, so the oldest one past this goes
ASK_LIFETIME = timedelta(minutes=10)    # a yes to a prompt left open longer than this runs nothing


@dataclass(frozen=True)
class Snapshot:
    """A file just before an Edit or Write, and the input the tool runs with, after io-guard's rewrites."""
    path: Path
    profile: Profile | None              # None for a file that does not exist yet
    data: bytes | None                   # the bytes too, for a file small enough to keep
    tool_input: Mapping[str, Any]


@dataclass(frozen=True)
class ShellSnapshot:
    """A repository's changes, and the size and time of each file the agent has read and of each file git
    status listed, just before a shell command."""
    root: Path | None                                  # None outside a repository
    status: frozenset[tuple[str, str]] | None          # (path from root, XY), None when git could not say
    stats: Mapping[Path, FileStat | None]
    listed: Mapping[Path, FileStat | None] = field(default_factory=dict)
    step: int = 0                                      # SessionState.step when the command started


@dataclass(eq=False)
class SessionState:
    """What io-guard learns during one session. One lock guards every field, because the io server runs
    several workers."""
    read_profiles: dict[Path, Profile] = field(default_factory=dict)   # the bytes last read or written
    snapshots: dict[str, Snapshot | ShellSnapshot] = field(default_factory=dict)   # by tool_use_id
    warned: set[str] = field(default_factory=set)                 # one user warning per key per session
    counts: dict[str, int] = field(default_factory=dict)          # how often each key happened
    budget_override: int | None = None                            # learned from an EOF failure
    first_cut: int | None = None                  # the shortest cut command's bytes, where no cut is known
    tracked: dict[Path, bool] = field(default_factory=dict)       # git's answer per path, asked once
    last_failed_build: str | None = None                          # the words of the build that last failed
    asked: dict[str, tuple[str, datetime]] = field(default_factory=dict)   # by tool_use_id: what, when
    tag: str | None = None                                        # the task the last io.snapshot named
    read_logs: dict[Path, tuple[int, int]] = field(default_factory=dict)   # io.read_log's line and byte
    dirty: tuple[Path, ...] | None = None                         # the files dirty at the first start
    step: int = 0                                                 # counts the steps below, in order
    own_writes: dict[Path, int] = field(default_factory=dict)     # the step of the session's last write
    shell_started: int = 0                                        # the step the last shell command started at
    lock: threading.RLock = field(default_factory=threading.RLock)
    data_dir: Path | None = None       # with a session id, the folder whose warned file the processes share
    session_id: str | None = None

    @classmethod
    def shared(cls, data_dir: Path | None, session_id: str) -> SessionState:
        """A session state whose warned keys every io-guard process of the session shares, the server and
        each command hook alike, through a file in io-guard's folder."""
        return cls(data_dir=data_dir, session_id=session_id if data_dir is not None else None)

    def first_time(self, key: str) -> bool:
        """True the first time a key is seen this session, in any of its processes, so a warning goes out
        once."""
        with self.lock:
            if key in self.warned:
                return False
            self.warned.add(key)
            if self.data_dir is None or self.session_id is None:
                return True
            try:
                return first_in_file(session_file(self.data_dir, self.session_id, "warned"), self.data_dir,
                                     key)
            except (OSError, TimeoutError) as error:
                log.debug("io-guard could not share the warning %s with the session's other processes: %s",
                          key, error)
                return True

    def count(self, key: str) -> int:
        """How many times key has been counted this session in this process, this time included."""
        with self.lock:
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

    def dirty_at_start(self) -> tuple[Path, ...] | None:
        """The files that had changes when the session first started, from sessions/<session>.dirty, which
        the session probe writes once per session id. A resume and a compaction keep the id, so they keep the
        list. None until the file exists."""
        with self.lock:
            if self.dirty is not None or self.data_dir is None or self.session_id is None:
                return self.dirty
            try:
                raw = json.loads(bytesio.read_bytes(session_file(self.data_dir, self.session_id, "dirty")))
            except (OSError, ValueError):
                return None
            self.dirty = tuple(Path(path) for path in raw)
            return self.dirty

    def next_step(self) -> int:
        with self.lock:
            self.step += 1
            return self.step

    def wrote(self, path: Path) -> None:
        """Record that the session's own Edit, Write or io tool wrote path, so a shell command running at
        the same time is not named for it."""
        with self.lock:
            self.own_writes[path] = self.next_step()

    def written_since(self, step: int) -> frozenset[Path]:
        with self.lock:
            return frozenset(path for path, at in self.own_writes.items() if at > step)

    def keep_snapshot(self, tool_use_id: str, snapshot: Snapshot | ShellSnapshot) -> None:
        """Keep what a call looked like before it ran, for its PostToolUse, until the PostToolUse takes it."""
        with self.lock:
            self.snapshots[tool_use_id] = snapshot
            while len(self.snapshots) > SNAPSHOTS_KEPT:
                del self.snapshots[next(iter(self.snapshots))]

    def peek_snapshot(self, tool_use_id: str) -> Snapshot | ShellSnapshot | None:
        """The snapshot kept for this call, left in the session for the check that takes it."""
        with self.lock:
            return self.snapshots.get(tool_use_id)

    def take_snapshot(self, tool_use_id: str) -> Snapshot | ShellSnapshot | None:
        """The snapshot kept for this call, removed from the session, or None."""
        with self.lock:
            return self.snapshots.pop(tool_use_id, None)

    def keep_ask(self, tool_use_id: str | None, key: str, now: datetime) -> None:
        """Record that a PreToolUse hook put the call tool_use_id, with the content key, to the user. A call
        with no id is never recorded, so its tool refuses it. Entries past ASK_LIFETIME go."""
        if tool_use_id is None:
            return
        with self.lock:
            self.asked = {each: (kept, at) for each, (kept, at) in self.asked.items()
                          if now - at <= ASK_LIFETIME}
            self.asked[tool_use_id] = (key, now)

    def take_ask(self, tool_use_id: str | None, key: str, now: datetime) -> bool:
        """True when the hook on this very call asked about this content within ASK_LIFETIME. The entry is
        spent either way, so one yes lets one call through."""
        if tool_use_id is None:
            return False
        with self.lock:
            found = self.asked.pop(tool_use_id, None)
        return found is not None and found[0] == key and now - found[1] <= ASK_LIFETIME


def first_in_file(path: Path, data_dir: Path, key: str) -> bool:
    """Add key to the file of keys at path, one JSON string a line, and say whether it was new. file_lock
    keeps two processes from both finding the key new."""
    line = json.dumps(key) + "\n"
    with locks.file_lock(path, data_dir, wait_s=1.0):
        if path.is_file() and line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as out:
            out.write(line)
    return True


def tracked(path: Path, git: GitPort, session: SessionState) -> bool | None:
    """Whether git tracks path, asked once per session until the session runs a git command. None when git
    cannot say."""
    with session.lock:
        if path in session.tracked:
            return session.tracked[path]
    try:
        answer = git.root(path) is not None and git.is_tracked(path)
    except GitError:
        return None
    with session.lock:
        session.tracked[path] = answer
    return answer
