"""The calls Claude Code refused before any hook ran, read from the end of the session's transcript.

Claude Code checks an Edit's or a Write's input before its hooks run, and a call it rejects there, such as an
old_string it cannot find, reaches no hook (context.md, "Hooks and MCP", row 30). The transcript still holds
the call's tool_use and its tool_result, whose text is wrapped in <tool_use_error>. The session's next hook
reads the transcript's last part and takes the refusals after the last tool result that was not one, so a
diagnosis reaches the model before it tries again. The transcript is Claude Code's own file, in a format it
does not document, so a line that does not parse, or a block of another shape, is skipped.
"""
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

REFUSED = re.compile(r"^<tool_use_error>(.*)</tool_use_error>$", re.S)


@dataclass(frozen=True)
class Refusal:
    tool_use_id: str
    tool: str
    tool_input: Mapping[str, Any]
    error: str                       # the text inside <tool_use_error>
    cwd: str | None                  # the session's folder when the call was made


def blocks(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    return [block for block in content if isinstance(block, Mapping)] if isinstance(content, list) else []


def result_text(block: Mapping[str, Any]) -> str:
    body = block.get("content")
    if isinstance(body, list):
        return "".join(part.get("text", "") for part in body if isinstance(part, Mapping))
    return body if isinstance(body, str) else ""


def refusals(tail: bytes) -> tuple[Refusal, ...]:
    """The refused calls in tail after the last tool result that was not a refusal, in order."""
    uses: dict[str, tuple[str, Mapping[str, Any], str | None]] = {}
    trailing: list[Refusal] = []
    for line in tail.split(b"\n"):
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, Mapping):
            continue
        for block in blocks(record):
            if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                given = block.get("input")
                uses[block["id"]] = (str(block.get("name", "")), given if isinstance(given, Mapping) else {},
                                     record.get("cwd"))
            elif block.get("type") == "tool_result":
                refused = REFUSED.match(result_text(block)) if block.get("is_error") else None
                call = uses.get(block.get("tool_use_id"))
                if refused is None or call is None:
                    trailing.clear()
                    continue
                trailing.append(Refusal(block["tool_use_id"], call[0], call[1], refused[1], call[2]))
    return tuple(trailing)
