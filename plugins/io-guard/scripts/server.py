"""io-guard's io server, as a stub in the legacy MCP era that serves the hook tools and nothing else.

The plugin's mcp_tool hooks call hook.pre_tool_use, hook.post_tool_use and hook.post_tool_use_failure. Each
call runs the check pipeline through hooks.bridge, which records it in telemetry and returns the answer as the
tool's text. A crash in a call answers with empty text, so the tool call goes on as if io-guard were absent.
Task 23 replaces this stub with the dual-era server, its io tools and its threads.
"""
import json
import sys

from ioguard.hooks import bridge

SERVER_INFO = {"name": "io-guard", "version": "0"}
HOOK_TOOLS = [{"name": name, "description": bridge.DESCRIPTION,
               "inputSchema": {"type": "object", "additionalProperties": True}} for name in bridge.TOOLS]
NO_DECISION = {"content": [{"type": "text", "text": ""}]}


def call_tool(params: dict) -> dict:
    if params.get("name") not in bridge.TOOLS:
        return {"content": [{"type": "text", "text": f"io-guard has no tool {params.get('name')}."}],
                "isError": True}
    return bridge.call(params.get("arguments") or {})


def handle(message: dict) -> dict | None:
    params = message.get("params") or {}
    match message.get("method"):
        case "initialize":
            return {"protocolVersion": params.get("protocolVersion"), "serverInfo": SERVER_INFO,
                    "capabilities": {"tools": {"listChanged": False}}}
        case "tools/list":
            return {"tools": HOOK_TOOLS}
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
        result = NO_DECISION if message.get("method") == "tools/call" else None
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
