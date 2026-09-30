"""What io-guard fixed, warned about and refused, summed from every session's telemetry file.

Each session writes events/<YYYY-MM>/<session>.jsonl in io-guard's folder (D13, D30). A line is one check's
result, which names the check and its code, or the run of a whole hook call, which names neither, carries
the call's time and lists the rewrites it applied in fixed, or an io tool call, event tools/call. A fix counts
from the hook call's own line, once. The printed report and the dashboard page both read a Summary. Its counts
and percentiles may go into a tool result, and its command heads may not, since a tool result lands in the
model's context.
"""
import json
import statistics
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ioguard.lib.program import program_name
from ioguard.lib.results import meanings
from ioguard.lib.telemetry import session_files

SEVERITIES = ("fixed", "warning", "refused", "info")
TOOL_CALL = "tools/call"
RECENT = 20                  # the latest lines kept per code


@dataclass
class Summary:
    first: datetime | None = None
    last: datetime | None = None
    sessions: set[str] = field(default_factory=set)
    lines: int = 0
    unreadable: int = 0
    events: Counter = field(default_factory=Counter)             # hook calls by event, and io tool calls
    codes: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))   # code -> severity -> n
    days: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))    # YYYY-MM-DD -> severity
    checks: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))  # check -> severity -> n
    tools: Counter = field(default_factory=Counter)
    projects: Counter = field(default_factory=Counter)
    platforms: Counter = field(default_factory=Counter)
    hook_ms: list[float] = field(default_factory=list)            # one per hook call
    io_ms: list[float] = field(default_factory=list)              # one per io tool call
    traces: dict[str, list[tuple[str, float]]] = field(default_factory=lambda: defaultdict(list))
    shapes: Counter = field(default_factory=Counter)             # command shapes behind refusals
    errors: Counter = field(default_factory=Counter)             # (where, error) of each GUARD_ERROR
    recent: dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=RECENT)))

    def counts(self) -> dict:
        """What a tool result may carry: counts and percentiles, no command, path or error text."""
        return {"sessions": len(self.sessions), "lines": self.lines, "events": dict(self.events),
                "codes": {code: dict(by) for code, by in self.codes.items()}, "tools": dict(self.tools),
                "platforms": dict(self.platforms), "hook_ms": spread(self.hook_ms),
                "io_ms": spread(self.io_ms), "use_ms": spread(uses(self.traces))}


def files(folders: Iterable[Path], since: datetime) -> list[Path]:
    """Every session file in the folders from the month of since on."""
    month = since.astimezone(timezone.utc).strftime("%Y-%m")
    return sorted(path for folder in folders for path in session_files(folder) if path.parent.name >= month)


def stamp(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def summarise(paths: Iterable[Path], since: datetime, project: str | None = None) -> Summary:
    """Every readable line from since on, of one project's calls when project names one."""
    summary = Summary()
    for path in paths:
        for raw in path.read_bytes().splitlines():
            try:
                line = json.loads(raw)
                when = stamp(line["ts"])
            except (ValueError, KeyError, TypeError):
                summary.unreadable += bool(raw.strip())
                continue
            if when is None or when < since or (project is not None and line.get("project") != project):
                continue
            add(summary, line, when)
    return summary


def add(summary: Summary, line: Mapping, when: datetime) -> None:
    summary.lines += 1
    summary.first = when if summary.first is None else min(summary.first, when)
    summary.last = when if summary.last is None else max(summary.last, when)
    summary.sessions.add(line.get("session") or "")
    code, check, event = line.get("code"), line.get("check"), line.get("event") or ""
    day = when.strftime("%Y-%m-%d")
    if code:
        severity = line.get("severity") or "warning"
        tally(summary, code, severity, day, line)
        summary.checks[check or line.get("tool") or "none"][severity] += 1
    if code == "GUARD_ERROR":
        summary.errors[(check or line.get("tool") or "?", line.get("error") or "")] += 1
    if line.get("severity") == "refused" and line.get("cmd_head"):
        summary.shapes[shape(line["cmd_head"])] += 1
    if check is not None or (code and event != TOOL_CALL):
        return
    for fix in line.get("fixed") or ():
        tally(summary, fix, "fixed", day, line)
    summary.events[event] += 1
    if line.get("tool"):
        summary.tools[line["tool"]] += 1
    summary.projects[line.get("project") or "none"] += 1
    summary.platforms[line.get("platform") or "none"] += 1
    took = line.get("latency_ms")
    if isinstance(took, (int, float)):
        (summary.io_ms if event == TOOL_CALL else summary.hook_ms).append(float(took))
        trace = (line.get("trace") or {}).get("trace_id")
        if trace:
            summary.traces[trace].append((line.get("tool") or "none", float(took)))


def tally(summary: Summary, code: str, severity: str, day: str, line: Mapping) -> None:
    summary.codes[code][severity] += 1
    summary.days[day][severity] += 1
    summary.recent[code].append(event_of(line, severity))


def event_of(line: Mapping, severity: str) -> dict:
    """One line as the dashboard lists it under its code."""
    return {"ts": line.get("ts"), "project": line.get("project"), "event": line.get("event"),
            "tool": line.get("tool"), "check": line.get("check"), "severity": severity,
            "command": line.get("cmd_head"), "file_ext": line.get("file_ext")}


def shape(command: str) -> str:
    """A command's program and, when it names one, its option or subcommand: sed -i, git status."""
    words = command.split()
    if not words:
        return ""
    head = program_name(words[0], (), fold=False)
    second = words[1] if len(words) > 1 else ""
    return f"{head} {second}" if second.startswith("-") or second.isalpha() and second.islower() else head


def uses(traces: Mapping[str, list[tuple[str, float]]]) -> list[float]:
    """The time of each tool use whose hooks ran more than once: its PreToolUse, PostToolUse and io call."""
    return [sum(took for _, took in calls) for calls in traces.values() if len(calls) > 1]


def spread(values: Sequence[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def at(share: float) -> float:
        return round(ordered[min(len(ordered) - 1, int(share * len(ordered)))], 1)
    return {"n": len(ordered), "p50": round(statistics.median(ordered), 1), "p90": at(0.9), "p95": at(0.95),
            "p99": at(0.99), "max": round(ordered[-1], 1)}


def page_data(summary: Summary, since: datetime, until: datetime) -> dict:
    """The summary as the dashboard page draws it, with every day from since to until, empty ones too."""
    first, last = (moment.astimezone(timezone.utc).date() for moment in (since, until))
    keys = [(first + timedelta(days=n)).isoformat() for n in range((last - first).days + 1)]
    days = [{"day": key, **{severity: summary.days.get(key, Counter()).get(severity, 0)
                            for severity in SEVERITIES}} for key in keys]
    return {"first": summary.first.isoformat() if summary.first else None,
            "last": summary.last.isoformat() if summary.last else None,
            "sessions": len(summary.sessions), "lines": summary.lines, "days": days,
            "codes": {code: dict(by) for code, by in summary.codes.items()},
            "checks": {check: dict(by) for check, by in summary.checks.items()},
            "projects": dict(summary.projects), "tools": dict(summary.tools), "events": dict(summary.events),
            "latency": {"hook": spread(summary.hook_ms), "io": spread(summary.io_ms),
                        "use": spread(uses(summary.traces))},
            "recent": {code: list(lines)[::-1] for code, lines in summary.recent.items()}}


def page(folders: Sequence[Path], days: int, now: datetime, project: str | None = None,
         start: datetime | None = None) -> dict:
    """The last days of telemetry as the dashboard page draws it, of one project when project names one, and
    from start on when it falls inside them, with each code's meaning and what the folders hold on disk."""
    window = now - timedelta(days=days)
    since = window if start is None else max(window, start)
    stored = [path.stat().st_size for folder in folders for path in session_files(folder)]
    return {**page_data(summarise(files(folders, since), since, project), window, now), "days_asked": days,
            "counted_from": None if start is None else start.isoformat(), "meanings": meanings(),
            "stored": {"files": len(stored), "bytes": sum(stored)}}
