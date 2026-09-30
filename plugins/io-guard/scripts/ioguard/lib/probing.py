"""The machine a session runs on: each tool's version, the console encoding, whether file names ignore
case, and the Claude Code version, measured here and kept as a Probe in probe.json. checks.session_probe
decides what to measure and saves it, and proc.on_path finds each tool.
"""
import json
import locale
import logging
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ioguard.lib import bytesio, proc
from ioguard.lib.platform import Platform

log = logging.getLogger("ioguard.lib")

AGENT = re.compile(r"claude-code_(\d+)-(\d+)-(\d+)")
EXECUTABLE = re.compile(r"[\\/](\d+\.\d+\.\d+)[\\/]claude(?:\.exe)?$", re.I)
WINDOWS_CUT = 7807          # bytes, apostrophes counted as four: the smallest Bash command cut on 2.1.281
FIXED_IN: str | None = None  # the first Claude Code release without the cut and the halving (#92543)
Runner = Callable[..., proc.RunResult]


def file_stamp(path: str) -> str | None:
    """The file's size and modification time, which change when the tool is replaced."""
    try:
        found = os.stat(path)
    except OSError:
        return None
    return f"{found.st_size}:{found.st_mtime_ns}"


@dataclass(frozen=True)
class ToolVersion:
    path: str
    version: str
    stamp: str | None = None     # the file's size and mtime when measured, so an unchanged tool is not rerun

    @classmethod
    def this_python(cls) -> ToolVersion:
        """The Python io-guard runs on, with its stamp."""
        version = ".".join(str(part) for part in sys.version_info[:3])
        return cls(sys.executable, version, file_stamp(sys.executable))


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
    taken_at: datetime | None

    @classmethod
    def unprobed(cls, platform: Platform) -> Probe:
        """What is known before the session probe has run: the platform and this Python."""
        return cls(os=platform.os, bash=None, pwsh=None, python=ToolVersion.this_python(), git=None,
                   console_encoding=None, fs_case_insensitive=platform.case_insensitive,
                   transport_budget=None, halving=None, claude_code_version=None, taken_at=None)

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> Probe:
        def version(key: str) -> ToolVersion | None:
            value = raw.get(key)
            return None if value is None else ToolVersion(value["path"], value["version"], value.get("stamp"))
        taken = raw.get("taken_at")
        return cls(os=raw["os"], bash=version("bash"), pwsh=version("pwsh"), python=version("python"),
                   git=version("git"), console_encoding=raw.get("console_encoding"),
                   fs_case_insensitive=raw["fs_case_insensitive"],
                   transport_budget=raw.get("transport_budget"),
                   halving=raw.get("halving"), claude_code_version=raw.get("claude_code_version"),
                   taken_at=None if taken is None else datetime.fromisoformat(taken))

    def to_json(self) -> dict:
        def version(tool: ToolVersion | None) -> dict | None:
            return None if tool is None else {"path": tool.path, "version": tool.version, "stamp": tool.stamp}
        return {"os": self.os, "bash": version(self.bash), "pwsh": version(self.pwsh),
                "python": version(self.python), "git": version(self.git),
                "console_encoding": self.console_encoding, "fs_case_insensitive": self.fs_case_insensitive,
                "transport_budget": self.transport_budget, "halving": self.halving,
                "claude_code_version": self.claude_code_version,
                "taken_at": None if self.taken_at is None else self.taken_at.isoformat()}


def load_probe(data_dir: Path | None, platform: Platform) -> Probe:
    """The probe the session probe saved, or the unprobed one when there is none or it cannot be read, which
    the next session probe writes again."""
    path = None if data_dir is None else data_dir / "probe.json"
    if path is None or not path.is_file():
        return Probe.unprobed(platform)
    try:
        return Probe.from_json(json.loads(bytesio.read_bytes(path).decode("utf-8")))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        log.warning("io-guard could not read %s, and runs unprobed until the session probe writes it: %s",
                    path, error)
        return Probe.unprobed(platform)


def tool_version(path: str, pattern: re.Pattern, previous: ToolVersion | None = None,
                 run: Runner = proc.run, timeout_s: float = 2.0) -> ToolVersion | None:
    """The version path --version prints, found by pattern's first group, run in the tool's own folder. A
    previous measure of the same unchanged file is kept without running anything. None when the tool fails or
    prints no version."""
    current = file_stamp(path)
    if previous is not None and current is not None and (previous.path, previous.stamp) == (path, current):
        return previous
    done = run([path, "--version"], Path(path).parent, timeout_s=timeout_s)
    match = pattern.search(done.stdout.decode("utf-8", "replace"))
    return ToolVersion(path, match[1], current) if done.ok and match else None


def claude_version(env: Mapping[str, str]) -> str | None:
    """The Claude Code version from the environment it gives its children, or None when it names none."""
    agent = AGENT.search(env.get("AI_AGENT", ""))
    if agent:
        return ".".join(agent.groups())
    executable = EXECUTABLE.search(env.get("CLAUDE_CODE_EXECPATH", ""))
    return executable[1] if executable else None


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def cut_applies(windows: bool, version: str | None) -> bool:
    """Whether the Bash tool's 8 KB cut and backslash halving apply to this session."""
    if not windows:
        return False
    if FIXED_IN is None or version is None:
        return True
    return version_tuple(version) < version_tuple(FIXED_IN)


def console_encoding() -> str:
    """The encoding a Python child prints through when nothing sets PYTHONUTF8 or PYTHONIOENCODING."""
    return locale.getencoding()


def case_insensitive(folder: Path, default: bool) -> bool:
    """Whether the file system under folder ignores case: the folder's name with its case swapped is the same
    folder. default answers for a name with no letters to swap."""
    swapped = Path(str(folder).swapcase())
    if str(swapped) == str(folder):
        return default
    try:
        return os.path.samefile(folder, swapped)
    except OSError:
        return False
