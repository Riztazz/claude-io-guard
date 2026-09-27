"""io-guard's io server, as a stub that proves the launch: a stdio MCP server in the legacy era.

It serves one tool, hook.pre_tool_use, which the plugin's PreToolUse mcp_tool hook calls. Each call writes one
line to the session's file under $IOGUARD_DATA/events/ and returns no decision, so the tool call goes on as if
io-guard were absent. Task 23 replaces it with the dual-era server and the real hook bridge.
"""
import json
import os
import sys
import time
from pathlib import Path

SERVER_INFO = {"name": "io-guard", "version": "0"}
HOOK_TOOL = {
    "name": "hook.pre_tool_use",
    "description": "Called by Claude Code hooks. Not for the model.",
    "inputSchema": {"type": "object", "additionalProperties": True},
}


def record(arguments: dict) -> None:
    data = os.environ.get("IOGUARD_DATA")
    if not data:
        return
    now = time.gmtime()
    session = str(arguments.get("session_id") or "unknown-session")
    folder = Path(data) / "events" / time.strftime("%Y-%m", now)
    folder.mkdir(parents=True, exist_ok=True)
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", now), "session": session,
            "event": arguments.get("hook_event_name"), "tool": arguments.get("tool_name"),
            "surface": "mcp_hook", "noop": True}
    with (folder / f"{session}.jsonl").open("ab") as out:
        out.write((json.dumps(line) + "\n").encode("ascii"))


def call_tool(params: dict) -> dict:
    if params.get("name") != HOOK_TOOL["name"]:
        return {"content": [{"type": "text", "text": f"io-guard has no tool {params.get('name')}."}],
                "isError": True}
    try:
        record(params.get("arguments") or {})
    except OSError as error:
        sys.stderr.write(f"io-guard could not record the hook call: {error}\n")
    return {"content": [{"type": "text", "text": ""}]}


def handle(message: dict) -> dict | None:
    params = message.get("params") or {}
    match message.get("method"):
        case "initialize":
            return {"protocolVersion": params.get("protocolVersion"), "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {"listChanged": False}}}
        case "tools/list":
            return {"tools": [HOOK_TOOL]}
        case "tools/call":
            return call_tool(params)
        case "ping":
            return {}
    return None


def reply(message: dict) -> dict:
    try:
        result = handle(message)
    except Exception as error:
        sys.stderr.write(f"io-guard's server failed on {message.get('method')}: {error!r}\n")
        no_decision = {"content": [{"type": "text", "text": ""}]}
        result = no_decision if message.get("method") == "tools/call" else None
    if result is None:
        missing = {"code": -32601, "message": f"io-guard has no method {message.get('method')}."}
        return {"jsonrpc": "2.0", "id": message["id"], "error": missing}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def serve() -> None:
    for line in sys.stdin.buffer:
        try:
            message = json.loads(line)
        except ValueError:
            sys.stderr.write("io-guard's server skipped a line that is not JSON.\n")
            continue
        if not isinstance(message, dict) or "id" not in message or "method" not in message:
            continue
        sys.stdout.buffer.write((json.dumps(reply(message)) + "\n").encode("ascii"))
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    serve()
