"""JSON-RPC for the io server in both MCP eras: the legacy initialize handshake, which Claude Code uses with a
stdio server by default, and the stateless 2026-07-28 protocol, which carries _meta on every request (D9).

The era is decided once per process. initialize makes it legacy, and the first request that carries a protocol
version in _meta makes it modern. server/discover answers in either and changes neither. A modern result
carries resultType and the server's info in _meta, because Claude Code's modern client rejects a result
without resultType, and its tools/list carries ttlMs and cacheScope for the same reason (context.md, "Hooks
and MCP", row 15). A legacy result carries none of them. A protocol failure is a JSON-RPC error. A tool's own
failure is a result with isError set, which ToolRegistry builds.
"""
import logging
import threading
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any

from ioguard.mcp.progress import CancelToken, ProgressReporter
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolRegistry

log = logging.getLogger("ioguard.mcp")

MODERN_VERSION = "2026-07-28"
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18")
SUPPORTED = (MODERN_VERSION, LEGACY_VERSIONS[0])
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_KEY = "io.modelcontextprotocol/serverInfo"
CAPABILITIES = {"tools": {"listChanged": False}}
TTL_MS = 300_000
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
UNSUPPORTED_VERSION = -32022


class Era(Enum):
    UNDECIDED = "undecided"
    LEGACY = "legacy"          # after initialize
    MODERN = "modern"          # after the first request with a protocol version in _meta


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


def error(ident: Any, code: int, message: str, data: Any = None) -> dict:
    body = {"code": code, "message": message}
    if data is not None:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": ident, "error": body}


class Protocol:
    """One request in, one response out, for the process's era. calls builds each tools/call's ToolCall."""

    def __init__(self, tools: ToolRegistry, server_info: Mapping[str, Any],
                 calls: Callable[[CancelToken], ToolCall]) -> None:
        self.tools, self.server_info, self.calls = tools, dict(server_info), calls
        self.state = Era.UNDECIDED
        self.lock = threading.Lock()

    def era(self) -> Era:
        with self.lock:
            return self.state

    def dispatch(self, message: Mapping[str, Any], cancel: CancelToken | None = None,
                 notify: Callable[[dict], None] | None = None) -> dict | None:
        """The response to a request, or None for a notification. notify sends a tool's progress to the
        client. Never raises: a bug is an internal error."""
        if "id" not in message:
            return None
        ident = message["id"]
        params = message.get("params") or {}
        try:
            if not isinstance(params, Mapping):
                raise RpcError(INVALID_PARAMS, "params must be an object.")
            result = self.handle(str(message.get("method")), params, cancel or CancelToken(), notify)
        except RpcError as failure:
            return error(ident, failure.code, failure.message, failure.data)
        except Exception:
            log.exception("GUARD_ERROR: io-guard's server failed on %s.", message.get("method"))
            return error(ident, INTERNAL_ERROR, f"io-guard failed on {message.get('method')}.")
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def handle(self, method: str, params: Mapping[str, Any], cancel: CancelToken,
               notify: Callable[[dict], None] | None = None) -> dict:
        if method == "server/discover":
            return self.modern({"supportedVersions": list(SUPPORTED), "capabilities": CAPABILITIES,
                                "serverInfo": self.server_info, "ttlMs": TTL_MS, "cacheScope": "private"})
        if method == "initialize":
            return self.initialize(params)
        modern = self.decide(params)
        match method:
            case "ping":
                body: dict = {}
            case "tools/list":
                body = {"tools": self.tools.list()}
                if modern:
                    body |= {"ttlMs": TTL_MS, "cacheScope": "private"}
            case "tools/call":
                body = self.call(params, cancel, notify)
            case "resources/list":
                body = {"resources": []}
            case _:
                raise RpcError(METHOD_NOT_FOUND, f"io-guard has no method {method}.")
        return self.modern(body) if modern else body

    def initialize(self, params: Mapping[str, Any]) -> dict:
        with self.lock:
            self.state = Era.LEGACY
        asked = params.get("protocolVersion")
        version = asked if asked in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
        return {"protocolVersion": version, "capabilities": CAPABILITIES, "serverInfo": self.server_info}

    def decide(self, params: Mapping[str, Any]) -> bool:
        """Whether the request runs under modern semantics, setting the era on the first modern request. A
        modern request without its _meta fields, or with a version io-guard lacks, is refused."""
        meta = params.get("_meta")
        meta = meta if isinstance(meta, Mapping) else {}
        version = meta.get(VERSION_KEY)
        with self.lock:
            if self.state is Era.UNDECIDED and version is not None:
                self.state = Era.MODERN
            era = self.state
        if era is not Era.MODERN:
            return False
        if version is None or CAPABILITIES_KEY not in meta:
            raise RpcError(INVALID_PARAMS, f"A {MODERN_VERSION} request carries {VERSION_KEY} and "
                                           f"{CAPABILITIES_KEY} in _meta.")
        if version != MODERN_VERSION:
            raise RpcError(UNSUPPORTED_VERSION, f"io-guard does not speak protocol version {version}.",
                           {"supported": list(SUPPORTED)})
        return True

    def call(self, params: Mapping[str, Any], cancel: CancelToken,
             notify: Callable[[dict], None] | None) -> dict:
        name, arguments = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, Mapping):
            raise RpcError(INVALID_PARAMS, "tools/call takes a name and an arguments object.")
        meta = params.get("_meta")
        token = meta.get("progressToken") if isinstance(meta, Mapping) else None
        call = self.calls(cancel)
        call.progress = ProgressReporter(notify, token)
        try:
            return self.tools.call(name, arguments, call)
        except InvalidArguments as failure:
            raise RpcError(INVALID_PARAMS, str(failure)) from None

    def modern(self, body: dict) -> dict:
        return {**body, "resultType": "complete", "_meta": {SERVER_KEY: self.server_info}}
