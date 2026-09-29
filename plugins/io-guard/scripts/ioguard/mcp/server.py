"""The io server: one process per Claude Code session, reading JSON-RPC lines from stdin and answering on
stdout.

The reader answers every quick method itself, so initialize, tools/list and the rest keep the order they came
in. Each tools/call goes to one of four workers, and a cancel notification sets that call's token. One lock
serialises the writes to stdout, and sys.stdout points at stderr, so no stray print corrupts an answer. A line
that is not JSON, or a request whose id or params has the wrong type, gets an error, and the loop goes on. A
watchdog rewrites the session's heartbeat every 5 seconds, which the UserPromptSubmit hook reads to tell the
user when the server died. At the end of stdin the server stops taking calls, waits up to 2 seconds for the
running ones, cancels what still runs, and marks the heartbeat stopped.
"""
import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, BinaryIO

from ioguard import PLUGIN_VERSION
from ioguard.lib import bytesio, retention, snapshots, telemetry
from ioguard.lib.context import Context, home_folder, session_file
from ioguard.lib.heartbeat import Heartbeat
from ioguard.mcp import (tools_dashboard, tools_edit, tools_format, tools_history, tools_hook, tools_read,
                         tools_run, tools_trust)
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.protocol import INVALID_REQUEST, PARSE_ERROR, Era, Protocol, error
from ioguard.mcp.toolspec import ToolCall, ToolRegistry

log = logging.getLogger("ioguard.mcp")

SERVER_INFO = {"name": "io-guard", "version": PLUGIN_VERSION}
WORKERS = 4
BEAT_S = 5.0
DRAIN_S = 2.0
CANCEL_S = 1.0          # after the drain, how long a cancelled call has to answer
SAVED = ("results", "runs", "bodies")      # the folders of io-guard's where a project's content is saved


def registry() -> ToolRegistry:
    """Every tool the server offers: the io tools first, and the hook tools last."""
    tools = ToolRegistry()
    for spec in (*tools_read.SPECS, *tools_edit.SPECS, *tools_run.SPECS, *tools_format.SPECS,
                 *tools_history.SPECS, *tools_dashboard.SPECS, *tools_trust.SPECS, *tools_hook.SPECS):
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

    def __init__(self, protocol: Protocol, out: BinaryIO, workers: int = WORKERS) -> None:
        self.protocol, self.out = protocol, out
        self.write_lock = threading.Lock()
        self.workers = ThreadPoolExecutor(workers, thread_name_prefix="io-guard worker")
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
        ident, params = message.get("id"), message.get("params")
        if not isinstance(ident, (str, int, type(None))) or not isinstance(params, (dict, type(None))):
            self.send(error(None, INVALID_REQUEST, "A request's id is a string or a number, and its params "
                                                   "an object."))
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
            request = (message.get("params") or {}).get("requestId")
            if not isinstance(request, (str, int)):
                return
            with self.state_lock:
                token = self.tokens.get(request)
            if token is not None:
                token.cancel()

    def work(self, message: dict, token: CancelToken) -> None:
        try:
            self.send(self.protocol.dispatch(message, token, self.send))
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
        """Take no more calls, give the running ones DRAIN_S seconds to answer, then cancel what still runs
        and give it CANCEL_S more. The worker threads are joined when the process ends, so a call nobody
        cancelled would hold the exit for as long as it runs."""
        with self.state_lock:
            running = set(self.running)
        _, left = wait(running, timeout=DRAIN_S)
        if left:
            with self.state_lock:
                tokens = list(self.tokens.values())
            for token in tokens:
                token.cancel()
            wait(left, timeout=CANCEL_S)
        self.workers.shutdown(wait=False, cancel_futures=True)


def expire(data: Path, context: Callable[[], Context], now: datetime) -> list[Path]:
    """Delete the telemetry files past telemetry.retention_days, and the entries of SAVED past io.saved_days,
    and cut the command heads of the telemetry files past telemetry.cmd_head_days, all from the user's
    config. The paths deleted."""
    config = context().config
    try:
        gone = telemetry.expire(data, config.get("telemetry.retention_days"), now)
        shrunk = telemetry.shrink_heads(data, config.get("telemetry.cmd_head_days"), now)
        if shrunk:
            log.info("io-guard cut the command heads of %d telemetry files to their programs", len(shrunk))
        swept = snapshots.sweep(data, now)
        if swept:
            log.info("io-guard deleted %d snapshots past their seven days", swept)
        days = config.get("io.saved_days")
        if days > 0:
            cutoff = now - timedelta(days=days)
            old = [entry for name in SAVED for entry in retention.older(data / name, cutoff)]
            gone += retention.delete(old)
    except OSError as failure:
        log.warning("io-guard could not delete what it kept in %s: %s", data, failure)
        return []
    if gone:
        log.info("io-guard deleted %d files and folders past their retention", len(gone))
    return gone


def main() -> int:
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    data = home_folder(os.environ)
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    cwd = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    spill = data / "results"
    named = session or "io-server"

    def context() -> Context:
        return tools_hook.context_for(named, cwd)

    protocol = Protocol(registry(), SERVER_INFO, lambda cancel: ToolCall(context, cancel, cwd, spill,
                                                                         session=named))
    threading.Thread(target=expire, args=(data, context, datetime.now(timezone.utc)),
                     name="io-guard retention", daemon=True).start()
    watchdog = None
    if session:
        watchdog = Watchdog(session_file(data, session, "alive"), session, protocol.era)
        watchdog.start()
    try:
        Server(protocol, out, context().config.get("io.server.workers")).serve(sys.stdin.buffer)
    finally:
        if watchdog is not None:
            watchdog.stop()
    return 0
