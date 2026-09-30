"""Measuring the machine a session runs on: each tool's version, the console encoding, whether file names
ignore case, and the Claude Code version. checks.session_probe decides what to measure and saves it, and
proc.on_path finds each tool.
"""
import locale
import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from ioguard.lib import proc
from ioguard.lib.context import ToolVersion, file_stamp

AGENT = re.compile(r"claude-code_(\d+)-(\d+)-(\d+)")
EXECUTABLE = re.compile(r"[\\/](\d+\.\d+\.\d+)[\\/]claude(?:\.exe)?$", re.I)
WINDOWS_CUT = 7807          # bytes, apostrophes counted as four: the smallest Bash command cut on 2.1.281
FIXED_IN: str | None = None  # the first Claude Code release without the cut and the halving (#92543)
Runner = Callable[..., proc.RunResult]


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
