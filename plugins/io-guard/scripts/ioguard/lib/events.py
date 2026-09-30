"""One hook event as io-guard sees it, from the harness JSON or from an mcp_tool hook's substituted map."""
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ioguard.lib import paths
from ioguard.lib.platform import Platform, detect


class EventError(ValueError):
    """The harness sent an event io-guard cannot read."""


def by_value[E: Enum](enum: type[E], value: str, fallback: E) -> E:
    """The member of enum whose value is value, or fallback for a value enum does not know, and for the
    fallback's own value, which names no real member."""
    return next((each for each in enum if each.value == value and each is not fallback), fallback)


class HookEvent(Enum):
    SESSION_START = "SessionStart"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"


class Tool(Enum):
    BASH = "Bash"
    POWERSHELL = "PowerShell"
    EDIT = "Edit"
    WRITE = "Write"
    READ = "Read"
    GREP = "Grep"
    GLOB = "Glob"
    OTHER = "other"

    @classmethod
    def named(cls, name: str) -> Tool:
        """The tool with this harness name, or OTHER for an MCP tool or a tool io-guard does not know."""
        return by_value(cls, name, cls.OTHER)


class PermissionMode(Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    AUTO = "auto"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"
    UNKNOWN = "unknown"          # a mode a later Claude Code adds, whose text stays in Event.raw

    @classmethod
    def named(cls, name: str) -> PermissionMode:
        return by_value(cls, name, cls.UNKNOWN)


class Surface(Enum):
    COMMAND_HOOK = "command_hook"
    MCP_HOOK = "mcp_hook"
    MCP_TOOL = "mcp_tool"
    CLI = "cli"


SCALAR_FIELDS = ("hook_event_name", "session_id", "tool_use_id", "prompt_id", "tool_name", "cwd",
                 "scratchpad_dir", "transcript_path", "permission_mode", "agent_id", "error")
WHOLE_FIELDS = ("tool_input", "tool_response")
SESSION_ID = re.compile(r"[A-Za-z0-9_-]+")      # it names io-guard's files for the session


def text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def member(enum: type[Enum], value: Any, what: str) -> Any:
    try:
        return enum(value)
    except ValueError:
        raise EventError(f"io-guard does not know the {what} {value!r}.") from None


@dataclass(frozen=True)
class Event:
    kind: HookEvent
    tool: Tool
    tool_name: str
    tool_input: Mapping[str, Any]
    tool_response: Mapping[str, Any] | None   # None when absent or not an object, and raw keeps the value
    error: str | None
    session_id: str
    tool_use_id: str | None
    prompt_id: str | None
    cwd: Path
    scratchpad: Path | None
    transcript: Path | None          # the session's transcript, which lib.transcript reads the end of
    permission_mode: PermissionMode
    agent_id: str | None
    surface: Surface
    raw: Mapping[str, Any]
    platform: Platform

    command: str | None              # Bash and PowerShell, from tool_input["command"]
    file_path: Path | None           # Edit, Write and Read, normalised once
    old_string: str | None
    new_string: str | None
    replace_all: bool
    content: str | None

    @classmethod
    def from_hook_json(cls, raw: Mapping[str, Any], surface: Surface,
                       platform: Platform | None = None) -> Event:
        platform = platform or detect()
        missing = [key for key in ("hook_event_name", "session_id", "cwd") if not text(raw.get(key))]
        if missing:
            raise EventError(f"The hook event lacks {', '.join(missing)}.")
        if not SESSION_ID.fullmatch(raw["session_id"]):
            raise EventError(f"The hook event's session_id {raw['session_id']!r} is not a plain name.")
        tool_input = raw.get("tool_input", {})
        if not isinstance(tool_input, Mapping):
            raise EventError(f"The hook event's tool_input is a {type(tool_input).__name__}, not an object.")
        response = raw.get("tool_response")
        cwd = Path(raw["cwd"])
        tool_name = text(raw.get("tool_name")) or ""
        return cls(
            kind=member(HookEvent, raw["hook_event_name"], "hook event"),
            tool=Tool.named(tool_name),
            tool_name=tool_name,
            tool_input=MappingProxyType(dict(tool_input)),
            tool_response=MappingProxyType(dict(response)) if isinstance(response, Mapping) else None,
            error=text(raw.get("error")),
            session_id=raw["session_id"],
            tool_use_id=text(raw.get("tool_use_id")),
            prompt_id=text(raw.get("prompt_id")),
            cwd=cwd,
            scratchpad=Path(raw["scratchpad_dir"]) if text(raw.get("scratchpad_dir")) else None,
            transcript=Path(raw["transcript_path"]) if text(raw.get("transcript_path")) else None,
            permission_mode=PermissionMode.named(text(raw.get("permission_mode")) or "default"),
            agent_id=text(raw.get("agent_id")),
            surface=surface,
            raw=MappingProxyType(dict(raw)),
            platform=platform,
            **derived(tool_input, cwd, platform),
        )

    @classmethod
    def from_fields(cls, fields: Mapping[str, str], platform: Platform | None = None) -> Event:
        """Rebuild an event from the map an mcp_tool hook passes.

        Every value arrives as a string, and an absent one as an empty string. tool_input and tool_response
        arrive whole, as JSON text, and are decoded here.
        """
        raw: dict[str, Any] = {key: fields[key] for key in SCALAR_FIELDS if fields.get(key)}
        for key in WHOLE_FIELDS:
            if fields.get(key):
                try:
                    raw[key] = json.loads(fields[key])
                except (ValueError, RecursionError) as error:
                    raise EventError(f"The mcp_tool hook's {key} is not JSON: {error}.") from None
        return cls.from_hook_json(raw, Surface.MCP_HOOK, platform)

    def with_tool_input(self, tool_input: Mapping[str, Any]) -> Event:
        """The same event with another tool_input, and its derived fields worked out again."""
        return replace(self, tool_input=MappingProxyType(dict(tool_input)),
                       **derived(tool_input, self.cwd, self.platform))


def derived(tool_input: Mapping[str, Any], cwd: Path, platform: Platform) -> dict[str, Any]:
    """The fields io-guard reads from tool_input, each None when absent or of the wrong type."""
    file_path = text(tool_input.get("file_path"))
    return {
        "command": text(tool_input.get("command")),
        "file_path": None if file_path is None else paths.normalise(file_path, cwd, platform),
        "old_string": text(tool_input.get("old_string")),
        "new_string": text(tool_input.get("new_string")),
        "replace_all": tool_input.get("replace_all") is True,
        "content": text(tool_input.get("content")),
    }
