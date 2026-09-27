"""One JSONL line per decision, in ${CLAUDE_PLUGIN_DATA}/events/<YYYY-MM>/<session>.jsonl.

A line holds codes, timings and names, never file content: no old_string, no new_string, and at most 200
characters of a command. The trace context joins the PreToolUse decision, an io tool call and the PostToolUse
check of one tool use.
"""
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ioguard import TELEMETRY_SCHEMA

COMMAND_HEAD = 200
TRACEPARENT = re.compile(r"^[0-9a-f]{2}-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    parent_span_id: str | None


def trace_from(tool_use_id: str | None, traceparent: str | None) -> TraceContext:
    """A W3C trace context: the caller's trace when a traceparent arrives, else one derived from the tool
    use, so every record about one tool use shares a trace id."""
    span_id = secrets.token_hex(8)
    match = TRACEPARENT.match(traceparent or "")
    if match:
        return TraceContext(match[1], span_id, match[2])
    if tool_use_id:
        return TraceContext(hashlib.sha256(tool_use_id.encode("utf-8")).hexdigest()[:32], span_id, None)
    return TraceContext(secrets.token_hex(16), span_id, None)


@dataclass(frozen=True)
class TelemetryEvent:
    ts: datetime
    session: str
    event: str
    surface: str
    platform: str
    project: str | None = None
    tool: str | None = None
    check: str | None = None
    code: str | None = None
    severity: str | None = None
    latency_ms: float | None = None
    fixed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    error: str | None = None
    tool_use_id: str | None = None
    agent_id: str | None = None
    prompt_id: str | None = None
    trace: TraceContext | None = None
    cmd_head: str | None = None
    file_ext: str | None = None
    bytes: int | None = None

    def to_json(self) -> dict:
        stamp = self.ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + \
            f"{self.ts.microsecond // 1000:03d}Z"
        return {
            "schema": TELEMETRY_SCHEMA, "ts": stamp, "session": self.session, "project": self.project,
            "platform": self.platform, "surface": self.surface, "event": self.event, "tool": self.tool,
            "check": self.check, "code": self.code, "severity": self.severity, "latency_ms": self.latency_ms,
            "fixed": list(self.fixed), "skipped": list(self.skipped), "error": self.error,
            "tool_use_id": self.tool_use_id, "agent_id": self.agent_id, "prompt_id": self.prompt_id,
            "trace": None if self.trace is None else {"trace_id": self.trace.trace_id,
                                                       "span_id": self.trace.span_id,
                                                       "parent_span_id": self.trace.parent_span_id},
            "cmd_head": None if self.cmd_head is None else self.cmd_head[:COMMAND_HEAD],
            "file_ext": self.file_ext, "bytes": self.bytes,
        }


class Telemetry:
    """Appends each event to its session's file, or keeps it in memory when there is no data folder."""

    def __init__(self, data_dir: Path | None, enabled: bool = True) -> None:
        self.data_dir = data_dir
        self.enabled = enabled
        self.events: list[TelemetryEvent] = []

    @classmethod
    def memory(cls) -> "Telemetry":
        return cls(None)

    def path_for(self, event: TelemetryEvent) -> Path:
        month = event.ts.astimezone(timezone.utc).strftime("%Y-%m")
        return self.data_dir / "events" / month / f"{event.session}.jsonl"

    def record(self, event: TelemetryEvent) -> None:
        if not self.enabled:
            return
        if self.data_dir is None:
            self.events.append(event)
            return
        path = self.path_for(event)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as out:
            out.write((json.dumps(event.to_json()) + "\n").encode("ascii"))

    def flush(self) -> None:
        """Each record is written and closed at once, so nothing waits. The io server queues records."""
