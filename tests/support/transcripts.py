"""Claude Code transcript lines shaped like the ones on disk, for building a corpus in a test.

The keys match what a transcript under ~/.claude/projects holds: a prompt entry carries permissionMode, an
assistant entry carries tool_use blocks, and the user entry after it carries tool_result and toolUseResult.
"""
import json
from pathlib import Path

SESSION = "11111111-1111-4111-8111-111111111111"
CWD = "C:\\project"


def prompt(text: str, mode: str = "default") -> dict:
    return {"type": "user", "sessionId": SESSION, "cwd": CWD, "permissionMode": mode,
            "timestamp": "2026-09-27T10:00:00.000Z", "message": {"role": "user", "content": text}}


def tool_use(use_id: str, name: str, tool_input: dict) -> dict:
    return {"type": "assistant", "sessionId": SESSION, "cwd": CWD, "version": "2.1.283",
            "timestamp": "2026-09-27T10:00:01.000Z",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": use_id, "name": name,
                                                          "input": tool_input}]}}


def tool_result(use_id: str, text: str, failed: bool = False, response=None) -> dict:
    entry = {"type": "user", "sessionId": SESSION, "cwd": CWD, "timestamp": "2026-09-27T10:00:02.000Z",
             "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": use_id,
                                                      "content": text, "is_error": failed}]}}
    if response is not None:
        entry["toolUseResult"] = response
    return entry


def write(path: Path, entries: list, extra: bytes = b"") -> Path:
    """Write the entries as a transcript, one JSON object per line, then any extra raw bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(json.dumps(entry).encode("ascii") + b"\n" for entry in entries) + extra)
    return path
