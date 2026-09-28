"""A stdio MCP server that records every message the client sends and answers both protocol eras.

It serves the tools the probes call: hook_gate for mcp_tool hooks, probe_permit for --permission-prompt-tool,
three tools that differ only in their annotations, one that elicits, one that reports progress, and one that
names a ui:// resource. The probe's settings are in probe.json at the plugin root.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import answers  # noqa: E402

PROBE = json.loads((ROOT / "probe.json").read_bytes())
LOG = Path(PROBE["log"])
NONCE = PROBE["nonce"]
MODERN = "2026-07-28"
APP_URI = "ui://io-probe/app.html"
APP_MIME = "text/html;profile=mcp-app"
APP_HTML = "<!doctype html><html><body><h1>io-probe app</h1><p>NONCE</p></body></html>"
OBJECT_SCHEMA = {"type": "object", "additionalProperties": True}
TOOLS = [
    {"name": "hook_gate", "description": "Answers an mcp_tool hook. Only hooks call it.",
     "inputSchema": OBJECT_SCHEMA},
    {"name": "probe_plain", "description": "Returns a marker. Has no annotations.",
     "inputSchema": OBJECT_SCHEMA},
    {"name": "probe_read", "description": "Returns a marker. Marked read-only.",
     "inputSchema": OBJECT_SCHEMA, "annotations": {"readOnlyHint": True}},
    {"name": "probe_destructive", "description": "Returns a marker. Marked destructive.",
     "inputSchema": OBJECT_SCHEMA, "annotations": {"readOnlyHint": False, "destructiveHint": True}},
    {"name": "probe_elicit", "description": "Asks the user one question, then returns the answer.",
     "inputSchema": OBJECT_SCHEMA},
    {"name": "probe_progress", "description": "Reports progress three times, then returns a marker.",
     "inputSchema": OBJECT_SCHEMA},
    {"name": "probe_app", "description": "Returns a marker and names an MCP App to show beside it.",
     "inputSchema": OBJECT_SCHEMA, "_meta": {"ui": {"resourceUri": APP_URI}}},
    {"name": "probe_permit",
     "description": "Answers a permission prompt. Only --permission-prompt-tool calls it.",
     "inputSchema": OBJECT_SCHEMA},
]
DEAD_MARKER = LOG.parent / "server-stays-dead.marker"


def record(line: dict) -> None:
    line = {"source": "server", "pid": os.getpid(), "ns": time.time_ns(), **line}
    with LOG.open("ab") as out:
        out.write((json.dumps(line) + "\n").encode("ascii"))


def send(message: dict) -> None:
    record({"sent": message})
    sys.stdout.buffer.write((json.dumps(message) + "\n").encode("ascii"))
    sys.stdout.buffer.flush()


def read_message() -> dict | None:
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    message = json.loads(line)
    record({"received": message})
    return message


def is_modern(message: dict) -> bool:
    meta = (message.get("params") or {}).get("_meta") or {}
    return "io.modelcontextprotocol/protocolVersion" in meta


def with_result_type(message: dict, result: dict) -> dict:
    """Add the resultType a 2026-07-28 client requires on every result."""
    return {**result, "resultType": "complete"} if is_modern(message) else result


def text_result(message: dict, text: str, **extra) -> dict:
    return with_result_type(message, {"content": [{"type": "text", "text": text}], **extra})


class Server:
    def __init__(self) -> None:
        self.gate_calls = 0
        self.pending: list[dict] = []

    def ask_client(self, method: str, params: dict) -> dict | None:
        """Send a request to the client and wait for its answer, keeping other messages for later."""
        request_id = f"io-probe-{time.time_ns()}"
        send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while (message := read_message()) is not None:
            if message.get("id") == request_id and "method" not in message:
                return message
            self.pending.append(message)
        return None

    def elicit(self, message: dict, params: dict) -> dict:
        form = {"mode": "form", "message": f"io-probe asks: type any word ({NONCE})",
                "requestedSchema": {"type": "object", "properties": {"word": {"type": "string"}}}}
        if not is_modern(message):
            answer = self.ask_client("elicitation/create", form)
            return text_result(message, f"IOPROBE-ELICIT-{NONCE} {json.dumps(answer)}")
        if "inputResponses" not in params:
            return {"resultType": "input_required", "requestState": f"io-probe-{NONCE}",
                    "inputRequests": {"word": {"method": "elicitation/create", "params": form}}}
        responses = json.dumps(params["inputResponses"])
        return text_result(message, f"IOPROBE-ELICIT-{NONCE} {responses} state={params.get('requestState')}")

    def progress(self, message: dict, params: dict) -> dict:
        token = (params.get("_meta") or {}).get("progressToken")
        for step in range(1, 4):
            if token is not None:
                send({"jsonrpc": "2.0", "method": "notifications/progress",
                      "params": {"progressToken": token, "progress": step, "total": 3,
                                 "message": f"step {step} of 3"}})
            time.sleep(0.5)
        return text_result(message, f"IOPROBE-PROGRESS-{NONCE} token={token!r}")

    def call_tool(self, message: dict) -> dict:
        params = message.get("params") or {}
        name, args = params.get("name"), params.get("arguments") or {}
        match name:
            case "hook_gate":
                self.gate_calls += 1
                event = {"hook_event_name": args.get("hook_event_name"), "tool_name": args.get("tool_name"),
                         "tool_input": {"command": args.get("command")}}
                reply = answers.answer(PROBE["mode"], event, NONCE)
                record({"gate_args": args, "gate_reply": reply})
                return text_result(message, "" if reply is None else json.dumps(reply))
            case "probe_elicit":
                return self.elicit(message, params)
            case "probe_progress":
                return self.progress(message, params)
            case "probe_permit":
                decision = {"behavior": "allow", "updatedInput": args.get("input") or {}}
                return text_result(message, json.dumps(decision))
            case "probe_plain" | "probe_read" | "probe_destructive" | "probe_app":
                return text_result(message, f"IOPROBE-{name.upper()}-{NONCE}",
                                   structuredContent={"tool": name, "nonce": NONCE})
        return text_result(message, f"unknown tool {name}", isError=True)

    def handle(self, message: dict) -> dict | None:
        params = message.get("params") or {}
        match message.get("method"):
            case "initialize":
                return {"protocolVersion": params.get("protocolVersion"),
                        "capabilities": {"tools": {"listChanged": False}, "resources": {}},
                        "serverInfo": {"name": "io-probe", "version": "0"}}
            case "server/discover":
                return {"supportedVersions": [MODERN], "capabilities": {"tools": {}, "resources": {}},
                        "serverInfo": {"name": "io-probe", "version": "0"}, "ttlMs": 60000,
                        "cacheScope": "private", "resultType": "complete"}
            case "tools/list":
                return with_result_type(message, {"tools": TOOLS, "ttlMs": 60000, "cacheScope": "private"})
            case "tools/call":
                return self.call_tool(message)
            case "resources/list":
                resource = {"uri": APP_URI, "name": "io-probe app", "mimeType": APP_MIME}
                return with_result_type(message, {"resources": [resource]})
            case "resources/read":
                page = {"uri": APP_URI, "mimeType": APP_MIME, "text": APP_HTML.replace("NONCE", NONCE)}
                return with_result_type(message, {"contents": [page]})
            case "ping":
                return with_result_type(message, {})
        return None

    def serve(self) -> None:
        env_keys = ("MCP_PROTOCOL_NEGOTIATION", "MCP_SDK_GENERATION", "CLAUDE_PLUGIN_ROOT",
                    "CLAUDE_PLUGIN_DATA")
        named = sorted(key for key in os.environ if key.startswith(("CLAUDE", "MCP", "AI_AGENT")))
        sessions = {key: os.environ[key] for key in named if "SESSION" in key}
        record({"started": sys.argv, "env": {key: os.environ.get(key) for key in env_keys},
                "env_names": named, "session_like": sessions})
        if PROBE.get("stay_dead") and DEAD_MARKER.exists():
            record({"dying": "stays dead after its first death"})
            sys.exit(3)
        die_after = PROBE.get("die_after_gate")
        while True:
            message = self.pending.pop(0) if self.pending else read_message()
            if message is None:
                record({"stdin_closed": True})
                return
            if "id" not in message or "method" not in message:
                continue
            result = self.handle(message)
            if result is None:
                missing = {"code": -32601, "message": f"io-probe has no method {message['method']}"}
                send({"jsonrpc": "2.0", "id": message["id"], "error": missing})
            else:
                send({"jsonrpc": "2.0", "id": message["id"], "result": result})
            if die_after is not None and message["method"] == "tools/call" and self.gate_calls >= die_after:
                record({"dying": "die_after_gate reached"})
                if PROBE.get("stay_dead"):
                    DEAD_MARKER.write_bytes(b"")
                os._exit(0)


if __name__ == "__main__":
    Server().serve()
