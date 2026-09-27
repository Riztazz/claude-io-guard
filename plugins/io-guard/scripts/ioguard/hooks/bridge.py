"""The hook tools' side of an mcp_tool hook: the substituted map in, the answer JSON out as the tool's text.

Claude Code reads that text exactly as it reads a command hook's stdout, and a deny in it blocks the call.
Every value in the map arrives as a string, and tool_input and tool_response arrive whole as JSON text, which
Event.from_fields decodes. The result never sets isError, because an error result shows a hook notice on every
call.
"""
import json
from collections.abc import Mapping
from typing import Any

from ioguard.checks.registry import Registry
from ioguard.hooks.entry import run_event
from ioguard.lib.context import Context
from ioguard.lib.events import Surface

TOOLS = ("hook.pre_tool_use", "hook.post_tool_use", "hook.post_tool_use_failure")
DESCRIPTION = "Called by Claude Code hooks. Not for the model."


def call(fields: Mapping[str, Any], ctx: Context | None = None, registry: Registry | None = None) -> dict:
    """The hook tool's MCP result for one substituted map."""
    reply = run_event(fields, Surface.MCP_HOOK, ctx, registry)
    return {"content": [{"type": "text", "text": json.dumps(reply, ensure_ascii=True)}]}
