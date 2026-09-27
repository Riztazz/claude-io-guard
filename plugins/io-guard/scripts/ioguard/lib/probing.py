"""Measuring the machine a session runs on: each tool's place and version, the console encoding, whether file
names ignore case, and the Claude Code version. checks.session_probe decides what to measure and saves it.
"""
import locale
import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from ioguard.lib import proc
from ioguard.lib.context import ToolVersion

AGENT = re.compile(r"claude-code_(\d+)-(\d+)-(\d+)")
EXECUTABLE = re.compile(r"[\\/](\d+\.\d+\.\d+)[\\/]claude(?:\.exe)?$", re.I)
Runner = Callable[..., proc.RunResult]


def stamp(path: str) -> str | None:
    """The file's size and modification time, which change when the tool is replaced."""
    try:
        found = os.stat(path)
    except OSError:
        return None
    return f"{found.st_size}:{found.st_mtime_ns}"


def tool_version(path: str, pattern: re.Pattern, previous: ToolVersion | None = None,
                 run: Runner = proc.run, timeout_s: float = 2.0) -> ToolVersion | None:
    """The version path --version prints, found by pattern's first group, run in the tool's own folder. A
    previous measure of the same unchanged file is kept without running anything. None when the tool fails or
    prints no version."""
    current = stamp(path)
    if previous is not None and current is not None and (previous.path, previous.stamp) == (path, current):
        return previous
    done = run([path, "--version"], Path(path).parent, timeout_s=timeout_s)
    match = pattern.search(done.stdout.decode("utf-8", "replace"))
    return ToolVersion(path, match[1], current) if done.ok and match else None


def find(name: str, env: Mapping[str, str], skip: Sequence[str] = ()) -> str | None:
    """The first name on the environment's PATH whose folder names none of skip, ignoring case."""
    for folder in env.get("PATH", "").split(os.pathsep):
        if not folder or any(part.lower() in folder.lower() for part in skip):
            continue
        found = shutil.which(name, path=folder)
        if found:
            return found
    return None


def claude_version(env: Mapping[str, str]) -> str | None:
    """The Claude Code version from the environment it gives its children, or None when it names none."""
    agent = AGENT.search(env.get("AI_AGENT", ""))
    if agent:
        return ".".join(agent.groups())
    executable = EXECUTABLE.search(env.get("CLAUDE_CODE_EXECPATH", ""))
    return executable[1] if executable else None


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version))


def this_python() -> ToolVersion:
    return ToolVersion(sys.executable, ".".join(str(part) for part in sys.version_info[:3]),
                       stamp(sys.executable))


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
