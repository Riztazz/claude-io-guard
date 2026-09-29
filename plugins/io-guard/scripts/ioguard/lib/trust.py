"""Which project commands the user approved, in trust.json in io-guard's folder.

A project's .claude/io-guard.json may name commands io-guard starts, verify and format. They run once the
user approved that exact set: trust.json holds, per project, the SHA-256 of the commands' canonical JSON and
when the user approved it. A command that changes, in a pull or by hand, changes the fingerprint, and the set
waits for approval again. A project is named by its resolved folder, so two spellings of one folder share an
approval.
"""
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from ioguard.lib import bytesio, commands, locks, paths
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Result
from ioguard.lib.text import quoted

TRUST_FILE = "trust.json"


def fingerprint(commands: Mapping[str, Any]) -> str:
    """The SHA-256 of commands as canonical JSON: sorted keys, ASCII, no spaces."""
    text = json.dumps(dict(commands), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


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


def inside(held: Mapping[str, Any], project: Path) -> list[str]:
    """The words of the held commands that name a file inside project, which a pull can change."""
    found = []
    for value in held.values():
        for name, entry in value.items():
            for argv in ([entry] if name.startswith(".") else entry.values()):
                for word in argv:
                    path = Path(word) if Path(word).is_absolute() else project / word
                    if path.is_file() and path.resolve().is_relative_to(project.resolve()):
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


def read(data_dir: Path) -> dict[str, Any]:
    """trust.json's object, or an empty one when it is missing or cannot be read."""
    try:
        raw = json.loads(bytesio.read_bytes(data_dir / TRUST_FILE).decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def approved(data_dir: Path, project: Path, commands: Mapping[str, Any]) -> bool:
    """Whether the user approved exactly these commands for project."""
    entry = read(data_dir).get(paths.resolved(project))
    return isinstance(entry, dict) and entry.get("sha256") == fingerprint(commands)


def approve(data_dir: Path, project: Path, commands: Mapping[str, Any], now: datetime) -> None:
    """Record the user's approval of these commands for project, in place of any earlier one."""
    path = data_dir / TRUST_FILE
    with locks.file_lock(path, data_dir):
        entries = read(data_dir)
        entries[paths.resolved(project)] = {"sha256": fingerprint(commands), "approved": now.isoformat(),
                                            "folder": project.as_posix()}
        path.parent.mkdir(parents=True, exist_ok=True)
        bytesio.write_atomic(path, (json.dumps(entries, indent=2, ensure_ascii=True) + "\n").encode("ascii"))
