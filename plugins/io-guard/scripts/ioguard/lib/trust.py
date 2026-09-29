"""Which project commands the user approved, in trust.json in io-guard's folder.

A project's .claude/io-guard.json may name commands io-guard starts, verify and format. They run once the
user approved that exact set: trust.json holds, per project, the SHA-256 of the commands' canonical JSON and
when the user approved it. A command that changes, in a pull or by hand, changes the fingerprint, and the set
waits for approval again. A project is named by its resolved folder, so two spellings of one folder share an
approval.
"""
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from ioguard.lib import bytesio, locks, paths

TRUST_FILE = "trust.json"


def fingerprint(commands: Mapping[str, Any]) -> str:
    """The SHA-256 of commands as canonical JSON: sorted keys, ASCII, no spaces."""
    text = json.dumps(dict(commands), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


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
