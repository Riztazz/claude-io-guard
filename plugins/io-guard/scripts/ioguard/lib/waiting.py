"""The project commands that wait for the user's approval, as io-guard names them to the model and the user.

A project's .claude/io-guard.json may name verify and format commands, which run once the user approved that
exact set (lib.trust). Until then the context holds them apart, and each is shown with every word the
project's file gives quoted as JSON, so a word cannot start a line or hide text in io-guard's own message.
"""
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ioguard.lib import commands, paths
from ioguard.lib.platform import Platform
from ioguard.lib.ports import FsPort
from ioguard.lib.results import Code, Result
from ioguard.lib.text import quoted
from ioguard.lib.trust import fingerprint


def listed(held: Mapping[str, Any]) -> list[str]:
    """Each held command as one line: its key, where it applies and its words, each word the project's file
    names quoted as JSON, such as verify ".py": "python" "x"."""
    lines = []
    for key, value in sorted(held.items()):
        for name, entry in sorted(value.items()):
            pairs = entry.items() if not name.startswith(".") else [(name, entry)]
            where = "" if name.startswith(".") else f" in {quoted(name)}"
            lines += [f"{key} {quoted(extension)}{where}: {' '.join(map(quoted, argv))}"
                      for extension, argv in sorted(pairs)]
    return lines


def inside(held: Mapping[str, Any], project: Path, fs: FsPort, platform: Platform) -> list[str]:
    """The words of the held commands that name a file inside project, which a pull can change. A word is
    read from project, and a file is inside by its real path, through any link on the way."""
    root = fs.link_target(project) or project
    found = []
    for value in held.values():
        for name, entry in value.items():
            for argv in ([entry] if name.startswith(".") else entry.values()):
                for word in argv:
                    path = paths.normalise(word, project, platform)
                    real = fs.link_target(path) or path
                    if fs.stat(path) is not None and not fs.is_dir(path) and real.is_relative_to(root):
                        found.append(word)
    return sorted(set(found))


def untrusted(held: Mapping[str, Any], key: str, path: Path, tool: str, platform: Platform,
              first_time: Callable[[str], bool]) -> Result | None:
    """PROJECT_COMMANDS_UNTRUSTED, when the project names a key command for path that the user has not
    approved and first_time says this set was not named yet, else None."""
    if commands.command_for(held.get(key, {}), path, platform) is None:
        return None
    if not first_time(f"untrusted:{fingerprint(held)}"):
        return None
    waiting = "; ".join(listed(held))
    return Result.of(Code.PROJECT_COMMANDS_UNTRUSTED, f"The project's .claude/io-guard.json names commands "
                     f"the user has not approved, so io-guard ran none of them: {waiting}.", tool,
                     platform.os, file=path)
