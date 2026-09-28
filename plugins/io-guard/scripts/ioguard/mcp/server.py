"""The io server: one process per Claude Code session, reading JSON-RPC lines from stdin and answering on
stdout.

The reader answers every quick method itself, so initialize, tools/list and the rest keep the order they came
in. Each tools/call goes to one of four workers, and a cancel notification sets that call's token. One lock
serialises the writes to stdout, and sys.stdout points at stderr, so no stray print corrupts an answer. A line
that is not JSON gets a parse error, and the loop goes on. A watchdog rewrites the session's heartbeat every 5
seconds, which the UserPromptSubmit hook reads to tell the user when the server died. At the end of stdin the
server stops taking calls, waits up to 2 seconds for the running ones, and marks the heartbeat stopped.
"""
import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

from ioguard import PLUGIN_VERSION
from ioguard.lib import bytesio
from ioguard.lib.context import plugin_data, session_file
from ioguard.lib.heartbeat import Heartbeat
from ioguard.mcp import tools_hook, tools_read
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.protocol import INVALID_REQUEST, PARSE_ERROR, Era, Protocol, error
from ioguard.mcp.toolspec import ToolCall, ToolRegistry

log = logging.getLogger("ioguard.mcp")

SERVER_INFO = {"name": "io-guard", "version": PLUGIN_VERSION}
WORKERS = 4
BEAT_S = 5.0
DRAIN_S = 2.0


def registry() -> ToolRegistry:
    """Every tool the server offers: the io tools first, and the hook tools last."""
    tools = ToolRegistry()
    for spec in (*tools_read.SPECS, *tools_hook.SPECS):
        tools.register(spec)
    return tools


class Watchdog(threading.Thread):
    """Rewrites the heartbeat every BEAT_S seconds until stopped, then marks it stopped."""

    def __init__(self, path: Path, session: str, era: Callable[[], Era]) -> None:
        super().__init__(name="io-guard watchdog", daemon=True)
        now = datetime.now(timezone.utc)
        self.path, self.era, self.halt = path, era, threading.Event()
        self.beat = Heartbeat(os.getpid(), session, era().value, now, now)

    def run(self) -> None:
        while True:
            self.write(self.beat.again(datetime.now(timezone.utc), self.era().value))
            if self.halt.wait(BEAT_S):
                return

    def stop(self) -> None:
        self.halt.set()
        self.join(BEAT_S)
        now = datetime.now(timezone.utc)
        self.write(Heartbeat(self.beat.pid, self.beat.session, self.era().value, self.beat.started, now, now))

    def write(self, beat: Heartbeat) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            bytesio.write_atomic(self.path, beat.encode())
            self.beat = beat
        except OSError as failure:
            log.warning("io-guard could not write its heartbeat %s: %s", self.path, failure)


class Server:
    """The loop between stdin and stdout for one protocol."""

    def __init__(self, protocol: Protocol, out: BinaryIO) -> None:
        self.protocol, self.out = protocol, out
        self.write_lock = threading.Lock()
        self.workers = ThreadPoolExecutor(WORKERS, thread_name_prefix="io-guard worker")
        self.tokens: dict[Any, CancelToken] = {}
        self.running: set[Future] = set()
        self.state_lock = threading.Lock()

    def send(self, message: dict | None) -> None:
        if message is None:
            return
        line = (json.dumps(message, ensure_ascii=True) + "\n").encode("ascii")
        with self.write_lock:
            self.out.write(line)
            self.out.flush()

    def take(self, line: bytes) -> None:
        """One line from stdin: answered here, handed to a worker, or a notification acted on."""
        try:
            message = json.loads(line)
        except ValueError:
            self.send(error(None, PARSE_ERROR, "io-guard could not parse that line as JSON."))
            return
        if not isinstance(message, dict) or "method" not in message:
            if isinstance(message, dict) and ("result" in message or "error" in message):
                return
            self.send(error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST,
                            "A request is a JSON object with a method."))
            return
        if "id" not in message:
            self.notified(message)
        elif message["method"] == "tools/call":
            token = CancelToken()
            with self.state_lock:
                self.tokens[message["id"]] = token
                future = self.workers.submit(self.work, message, token)
                self.running.add(future)
            future.add_done_callback(self.finished)
        else:
            self.send(self.protocol.dispatch(message))

    def notified(self, message: dict) -> None:
        if message["method"] == "notifications/cancelled":
            params = message.get("params") or {}
            with self.state_lock:
                token = self.tokens.get(params.get("requestId"))
            if token is not None:
                token.cancel()

    def work(self, message: dict, token: CancelToken) -> None:
        try:
            self.send(self.protocol.dispatch(message, token))
        finally:
            with self.state_lock:
                self.tokens.pop(message["id"], None)

    def finished(self, future: Future) -> None:
        with self.state_lock:
            self.running.discard(future)

    def serve(self, stream: BinaryIO) -> None:
        for line in stream:
            if line.strip():
                self.take(line)
        self.stop()

    def stop(self) -> None:
        """Take no more calls, and give the running ones DRAIN_S seconds to answer."""
        with self.state_lock:
            running = set(self.running)
        wait(running, timeout=DRAIN_S)
        self.workers.shutdown(wait=False, cancel_futures=True)


def main() -> int:
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    data = plugin_data(os.environ)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    cwd = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    spill = None if data is None else data / "results"
    protocol = Protocol(registry(), SERVER_INFO,
                        lambda cancel: ToolCall(lambda: tools_hook.context_for(session or "io-server", cwd),
                                                cancel, cwd, spill))
    watchdog = None
    if data is not None and session:
        watchdog = Watchdog(session_file(data, session, "alive"), session, protocol.era)
        watchdog.start()
    try:
        Server(protocol, out).serve(sys.stdin.buffer)
    finally:
        if watchdog is not None:
            watchdog.stop()
    return 0
