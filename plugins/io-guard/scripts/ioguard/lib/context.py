"""Everything a check may read: the config, the probe, the platform, and ports to git, files and the clock.

A check receives a Context and reads it. No check writes into it except the session state, through its typed
fields. Context.live builds the real ports, and Context.fake builds in-memory ones for tests.
"""
import json
import os
import stat as stat_module
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from ioguard.lib import bytesio
from ioguard.lib.config import Config, ConfigKey, ConfigLayer, LoadReport, Scope, defaults, load
from ioguard.lib.git import Git, GitStatus, LineRange
from ioguard.lib.platform import Platform, detect
from ioguard.lib.telemetry import Telemetry


@dataclass(frozen=True)
class FileStat:
    size: int
    mtime_ns: int
    readonly: bool


@dataclass(frozen=True)
class Process:
    pid: int
    name: str


@dataclass(frozen=True)
class ToolVersion:
    path: str
    version: str


class GitPort(Protocol):
    def root(self, path: Path) -> Path | None: ...
    def is_tracked(self, path: Path) -> bool: ...
    def status(self, root: Path) -> GitStatus: ...
    def ls_files(self, root: Path) -> tuple[Path, ...]: ...
    def changed_ranges(self, path: Path) -> tuple[LineRange, ...]: ...
    def attributes(self, path: Path) -> Mapping[str, str]: ...


class FsPort(Protocol):
    def read_bytes(self, path: Path, limit: int | None = None) -> bytes: ...
    def write_atomic(self, path: Path, data: bytes) -> bytesio.WriteReport: ...
    def stat(self, path: Path) -> FileStat | None: ...
    def exists(self, path: Path) -> bool: ...
    def holders(self, path: Path) -> tuple[Process, ...]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...


@dataclass(frozen=True)
class Probe:
    """What the session probe found about this machine. Task 10 takes it at SessionStart and saves it as
    probe.json in the plugin data folder. A field io-guard has not probed is None."""
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
    dirty_at_start: tuple[Path, ...]
    taken_at: datetime | None

    @classmethod
    def unprobed(cls, platform: Platform) -> "Probe":
        """What is known before task 10's probe has run: the platform and this Python."""
        python = ToolVersion(sys.executable, ".".join(str(part) for part in sys.version_info[:3]))
        return cls(os=platform.os, bash=None, pwsh=None, python=python, git=None, console_encoding=None,
                   fs_case_insensitive=platform.case_insensitive, transport_budget=None, halving=None,
                   claude_code_version=None, dirty_at_start=(), taken_at=None)

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "Probe":
        def version(key: str) -> ToolVersion | None:
            value = raw.get(key)
            return None if value is None else ToolVersion(value["path"], value["version"])
        taken = raw.get("taken_at")
        return cls(os=raw["os"], bash=version("bash"), pwsh=version("pwsh"), python=version("python"),
                   git=version("git"), console_encoding=raw.get("console_encoding"),
                   fs_case_insensitive=raw["fs_case_insensitive"],
                   transport_budget=raw.get("transport_budget"),
                   halving=raw.get("halving"), claude_code_version=raw.get("claude_code_version"),
                   dirty_at_start=tuple(Path(path) for path in raw.get("dirty_at_start", ())),
                   taken_at=None if taken is None else datetime.fromisoformat(taken))


@dataclass(eq=False)
class SessionState:
    """What io-guard learns during one session. One lock guards every field, because the io server runs
    several workers."""
    read_hashes: dict[Path, str] = field(default_factory=dict)    # sha256 of the bytes the agent last saw
    snapshots: dict[Path, Any] = field(default_factory=dict)      # task 18 defines the snapshot
    warned: set[str] = field(default_factory=set)                 # one user warning per key per session
    budget_override: int | None = None                            # learned from an EOF failure
    last_failed_build: datetime | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)

    def first_time(self, key: str) -> bool:
        """True the first time a key is seen this session, so a warning goes out once."""
        with self.lock:
            if key in self.warned:
                return False
            self.warned.add(key)
            return True


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


class LiveFs:
    """The file system, through lib.bytesio."""

    def read_bytes(self, path: Path, limit: int | None = None) -> bytes:
        return bytesio.read_bytes(path, limit)

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
        raise NotImplementedError("Finding the process that holds a file arrives with lib.locks in task 19.")


def load_probe(data_dir: Path, platform: Platform) -> Probe:
    path = data_dir / "probe.json"
    if not path.is_file():
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

    @classmethod
    def live(cls, data_dir: Path, project: Path,
             check_keys: Mapping[str, Mapping[str, ConfigKey]] | None = None) -> "Context":
        """The real ports, the config from its four layers, and the probe from the plugin data folder."""
        platform = detect()
        layers = (ConfigLayer(Scope.USER, data_dir / "config.json"),
                  ConfigLayer(Scope.PROJECT, project / ".claude" / "io-guard.json"),
                  ConfigLayer(Scope.PROJECT_LOCAL, project / ".claude" / "io-guard.local.json"))
        report = load(layers, check_keys or {})
        return cls(config=report.config, probe=load_probe(data_dir, platform), platform=platform, git=Git(),
                   fs=LiveFs(), clock=SystemClock(), session=SessionState(),
                   telemetry=Telemetry(data_dir, enabled=report.config.get("telemetry.enabled")),
                   config_report=report)

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
