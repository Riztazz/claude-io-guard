"""Everything a check may read: the config, the probe, the platform, and ports to git, files and the clock.

A check receives a Context and reads it. No check writes into it except the session state, through its typed
fields. Context.live builds the real ports, and Context.fake builds in-memory ones for tests.
"""
import json
import logging
import os
import stat as stat_module
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from ioguard.lib import bytesio, locks, paths
from ioguard.lib.config import Config, ConfigKey, ConfigLayer, LoadReport, Scope, defaults, load
from ioguard.lib.git import Git, GitError, GitStatus, LineRange
from ioguard.lib.locks import Process
from ioguard.lib.platform import Platform, detect
from ioguard.lib.profile import Profile
from ioguard.lib.telemetry import Telemetry

log = logging.getLogger("ioguard.lib")


@dataclass(frozen=True)
class FileStat:
    size: int
    mtime_ns: int
    readonly: bool


@dataclass(frozen=True)
class ToolVersion:
    path: str
    version: str
    stamp: str | None = None     # the file's size and mtime when measured, so an unchanged tool is not rerun


class GitPort(Protocol):
    def root(self, path: Path) -> Path | None: ...
    def is_tracked(self, path: Path) -> bool: ...
    def status(self, root: Path) -> GitStatus: ...
    def ls_files(self, root: Path) -> tuple[Path, ...]: ...
    def changed_ranges(self, path: Path) -> tuple[LineRange, ...] | None: ...   # since HEAD, None untracked
    def attributes(self, path: Path) -> Mapping[str, str]: ...
    def staged(self, root: Path) -> tuple[str, ...]: ...
    def blob(self, root: Path, spec: str) -> bytes | None: ...


class FsPort(Protocol):
    def read_bytes(self, path: Path, limit: int | None = None) -> bytes: ...
    def read_tail(self, path: Path, limit: int) -> bytes: ...  # the last whole lines within limit bytes
    def read_from(self, path: Path, offset: int, limit: int) -> bytes: ...   # limit bytes from offset on
    def write_atomic(self, path: Path, data: bytes) -> bytesio.WriteReport: ...
    def stat(self, path: Path) -> FileStat | None: ...
    def exists(self, path: Path) -> bool: ...
    def holders(self, path: Path) -> tuple[Process, ...]: ...  # OSError when the platform cannot answer
    def make_folders(self, path: Path) -> None: ...
    def list_dir(self, path: Path) -> tuple[Path, ...]: ...    # the files in a folder, sorted, () when none
    def link_target(self, path: Path) -> Path | None: ...      # where a path through a link really is
    def find_named(self, root: Path, name: str, limit: int) -> tuple[Path, ...]: ...
                                                               # files named name under root, in limit entries
    def files_under(self, root: Path, limit: int) -> tuple[Path, ...]: ...
                                                               # sorted, outside .git, at most limit + 1


class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


@dataclass(frozen=True)
class Probe:
    """What the session probe found about this machine. checks.session_probe takes it at SessionStart and
    saves it as probe.json in io-guard's folder. A field io-guard has not probed is None."""
    os: str
    bash: ToolVersion | None
    pwsh: ToolVersion | None
    python: ToolVersion
    git: ToolVersion | None
    console_encoding: str | None
    fs_case_insensitive: bool
    transport_budget: int | None     # bytes, None where no cut exists or none was measured
    halving: bool | None             # whether the Bash tool halves backslashes, None when not probed
    claude_code_version: str | None
    dirty_at_start: tuple[Path, ...] | None   # None when git could not answer, () outside a repository
    taken_at: datetime | None

    @classmethod
    def unprobed(cls, platform: Platform) -> "Probe":
        """What is known before the session probe has run: the platform and this Python."""
        python = ToolVersion(sys.executable, ".".join(str(part) for part in sys.version_info[:3]))
        return cls(os=platform.os, bash=None, pwsh=None, python=python, git=None, console_encoding=None,
                   fs_case_insensitive=platform.case_insensitive, transport_budget=None, halving=None,
                   claude_code_version=None, dirty_at_start=None, taken_at=None)

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "Probe":
        def version(key: str) -> ToolVersion | None:
            value = raw.get(key)
            return None if value is None else ToolVersion(value["path"], value["version"], value.get("stamp"))
        taken, dirty = raw.get("taken_at"), raw.get("dirty_at_start")
        return cls(os=raw["os"], bash=version("bash"), pwsh=version("pwsh"), python=version("python"),
                   git=version("git"), console_encoding=raw.get("console_encoding"),
                   fs_case_insensitive=raw["fs_case_insensitive"],
                   transport_budget=raw.get("transport_budget"),
                   halving=raw.get("halving"), claude_code_version=raw.get("claude_code_version"),
                   dirty_at_start=None if dirty is None else tuple(Path(path) for path in dirty),
                   taken_at=None if taken is None else datetime.fromisoformat(taken))

    def to_json(self) -> dict:
        def version(tool: ToolVersion | None) -> dict | None:
            return None if tool is None else {"path": tool.path, "version": tool.version, "stamp": tool.stamp}
        dirty = self.dirty_at_start
        return {"os": self.os, "bash": version(self.bash), "pwsh": version(self.pwsh),
                "python": version(self.python), "git": version(self.git),
                "console_encoding": self.console_encoding, "fs_case_insensitive": self.fs_case_insensitive,
                "transport_budget": self.transport_budget, "halving": self.halving,
                "claude_code_version": self.claude_code_version,
                "dirty_at_start": None if dirty is None else [str(path) for path in dirty],
                "taken_at": None if self.taken_at is None else self.taken_at.isoformat()}


@dataclass(frozen=True)
class Snapshot:
    """A file just before an Edit or Write, and the input the tool runs with, after io-guard's rewrites."""
    path: Path
    profile: Profile | None              # None for a file that does not exist yet
    data: bytes | None                   # the bytes too, for a file small enough to keep
    tool_input: Mapping[str, Any]


@dataclass(frozen=True)
class ShellSnapshot:
    """A repository's changes, and the size and time of each file the agent has read, just before a shell
    command."""
    root: Path | None                                  # None outside a repository
    status: frozenset[tuple[str, str]] | None          # (path from root, XY), None when git could not say
    stats: Mapping[Path, FileStat | None]


SNAPSHOTS_KEPT = 16     # a call the user refuses leaves its snapshot, so the oldest one past this goes


@dataclass(eq=False)
class SessionState:
    """What io-guard learns during one session. One lock guards every field, because the io server runs
    several workers."""
    read_profiles: dict[Path, Profile] = field(default_factory=dict)   # the bytes last read or written
    snapshots: dict[str, Snapshot | ShellSnapshot] = field(default_factory=dict)   # by tool_use_id
    warned: set[str] = field(default_factory=set)                 # one user warning per key per session
    budget_override: int | None = None                            # learned from an EOF failure
    tracked: dict[Path, bool] = field(default_factory=dict)       # git's answer per path, asked once
    last_failed_build: str | None = None                          # the words of the build that last failed
    asked_runs: set[str] = field(default_factory=set)             # io.run calls the hook put to the user
    asked_restores: set[str] = field(default_factory=set)         # io.restore calls the hook put to the user
    tag: str | None = None                                        # the task the last io.snapshot named
    read_logs: dict[Path, tuple[int, int]] = field(default_factory=dict)   # io.read_log's line and byte
    lock: threading.RLock = field(default_factory=threading.RLock)
    data_dir: Path | None = None       # with a session id, the folder whose warned file the processes share
    session_id: str | None = None

    @classmethod
    def shared(cls, data_dir: Path | None, session_id: str) -> "SessionState":
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

    def stat(self, path: Path) -> FileStat | None:
        try:
            found = os.stat(path)
        except FileNotFoundError:
            return None
        return FileStat(found.st_size, found.st_mtime_ns, not found.st_mode & stat_module.S_IWRITE)

    def exists(self, path: Path) -> bool:
        return path.exists()

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

    def files_under(self, root: Path, limit: int) -> tuple[Path, ...]:
        """Every file under root, outside .git folders, sorted. A walk stops once it holds more than limit,
        so a caller sees that the folder holds more."""
        found: list[Path] = []
        for folder, folders, files in os.walk(root):
            folders[:] = sorted(child for child in folders if child != ".git")
            found += [Path(folder) / file for file in files]
            if len(found) > limit:
                break
        return tuple(sorted(found)[:limit + 1])


def read_or_none(fs: FsPort, path: Path) -> bytes | None:
    """path's bytes, or None when it is gone or cannot be read."""
    try:
        return fs.read_bytes(path)
    except OSError:
        return None


def session_file(data_dir: Path, session_id: str, kind: str) -> Path:
    """A file the session's io-guard processes share: sessions/<session>.<kind> in io-guard's folder."""
    return data_dir / "sessions" / f"{session_id}.{kind}"


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


def repository_root(git: GitPort, path: Path) -> Path | None:
    """The repository that holds path, or None outside one or when git cannot say."""
    try:
        return git.root(path)
    except GitError:
        return None


def home_folder(env: Mapping[str, str]) -> Path:
    """io-guard's folder, which every copy of the plugin on the machine shares, whatever id Claude Code gives
    it: IOGUARD_HOME, then io-guard in CLAUDE_CONFIG_DIR, then ~/.claude/io-guard. It holds the user's
    config.json, the file locks, the telemetry and the session files."""
    if env.get("IOGUARD_HOME"):
        return Path(env["IOGUARD_HOME"])
    if env.get("CLAUDE_CONFIG_DIR"):
        return Path(env["CLAUDE_CONFIG_DIR"]) / "io-guard"
    return Path.home() / ".claude" / "io-guard"


def load_probe(data_dir: Path | None, platform: Platform) -> Probe:
    path = None if data_dir is None else data_dir / "probe.json"
    if path is None or not path.is_file():
        return Probe.unprobed(platform)
    return Probe.from_json(json.loads(bytesio.read_bytes(path).decode("utf-8")))


@dataclass(frozen=True)
class Context:
    config: Config
    probe: Probe
    platform: Platform
    git: GitPort
    fs: FsPort
    clock: Clock
    session: SessionState
    telemetry: Telemetry
    config_report: LoadReport | None = None
    env: Mapping[str, str] = field(default_factory=dict)   # the environment, so no check reads os.environ
    data_dir: Path | None = None                           # io-guard's folder, None in a fake or a replay

    @classmethod
    def live(cls, data_dir: Path | None, project: Path,
             check_keys: Mapping[str, Mapping[str, ConfigKey]] | None = None) -> "Context":
        """The real ports, the config from its four layers, and the probe from io-guard's folder. With no
        folder there is no user layer and no probe, and telemetry stays in memory."""
        platform = detect()
        user = () if data_dir is None else (ConfigLayer(Scope.USER, data_dir / "config.json"),)
        layers = (*user, ConfigLayer(Scope.PROJECT, project / ".claude" / "io-guard.json"),
                  ConfigLayer(Scope.PROJECT_LOCAL, project / ".claude" / "io-guard.local.json"))
        report = load(layers, check_keys or {})
        return cls(config=report.config, probe=load_probe(data_dir, platform), platform=platform, git=Git(),
                   fs=LiveFs(), clock=SystemClock(), session=SessionState(),
                   telemetry=Telemetry(data_dir, enabled=report.config.get("telemetry.enabled")),
                   config_report=report, env=MappingProxyType(dict(os.environ)), data_dir=data_dir)

    @classmethod
    def fake(cls, files: Mapping[Path, bytes] | None = None, **overrides: Any) -> "Context":
        """In-memory ports for a test: a fake file system holding files, a fake git and a clock that only
        moves when told. Any field can be replaced by name."""
        from ioguard.lib.fakes import FakeClock, FakeFs, FakeGit
        platform = overrides.pop("platform", detect())
        built = dict(config=defaults(), probe=Probe.unprobed(platform), platform=platform, git=FakeGit(),
                     fs=FakeFs(files or {}), clock=FakeClock(), session=SessionState(),
                     telemetry=Telemetry.memory())
        built.update(overrides)
        return cls(**built)
