"""The hook tools: the mcp_tool hooks' way into the check pipeline, and a ping that shows the server answers.

hook.pre_tool_use, hook.post_tool_use and hook.post_tool_use_failure hand the substituted map to hooks.bridge,
the one import between two ways in, and return its answer as their text. They never set isError, because an
error result shows a hook notice on every call. They come last in tools/list, because the model never calls
them. context_for gives the io tools the live context the hook calls of the same session use.
"""
from pathlib import Path

from ioguard.hooks.bridge import DESCRIPTION, TOOLS, call, context
from ioguard.lib.context import Context
from ioguard.mcp.toolspec import NO_DECISION, ToolSpec

TITLES = {"hook.pre_tool_use": "Hook: before a tool call", "hook.post_tool_use": "Hook: after a tool call",
          "hook.post_tool_use_failure": "Hook: after a failed tool call"}


def hook(name: str) -> ToolSpec:
    return ToolSpec(name, TITLES[name], DESCRIPTION, input=None, output=None, read_only=True,
                    destructive=False, idempotent=False, handler=lambda arguments, given: call(arguments))


SPECS = (*(hook(name) for name in TOOLS),
         ToolSpec("hook.ping", "Hook: ping", DESCRIPTION, input=None, output=None, read_only=True,
                  destructive=False, idempotent=True, handler=lambda arguments, given: NO_DECISION))


def context_for(session_id: str, cwd: Path) -> Context:
    return context(session_id, cwd)
