"""The report of what io-guard fixed, warned about and refused, merged from every session's telemetry file.

Each session writes events/<YYYY-MM>/<session>.jsonl in io-guard's folder (D13, D30). A line is one check's
decision, which names the check and its code, or the run of a whole hook call, which names neither and
carries the call's time, or an io tool call, event tools/call. The printed report holds command shapes and
error hashes, so it goes to a terminal only. A tool result built from it takes the counts and percentiles and
nothing else, because a tool result lands in the model's context.
"""
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEVERITIES = ("fixed", "warning", "refused", "info")
COLUMNS = {"fixed": "fixed", "warning": "warned", "refused": "refused", "info": "info"}
TOOL_CALL = "tools/call"
SHOWN_CODES = 12
SHOWN_SHAPES = 5
SHOWN_ERRORS = 8
WIDTH = 110


@dataclass
class Report:
    first: datetime | None = None
    last: datetime | None = None
    sessions: set[str] = field(default_factory=set)
    lines: int = 0
    unreadable: int = 0
    events: Counter = field(default_factory=Counter)             # hook calls by event, and io tool calls
    codes: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))   # code -> severity -> n
    tools: Counter = field(default_factory=Counter)
    projects: Counter = field(default_factory=Counter)
    platforms: Counter = field(default_factory=Counter)
    hook_ms: list[float] = field(default_factory=list)            # one per hook call
    io_ms: list[float] = field(default_factory=list)              # one per io tool call
    traces: dict[str, list[tuple[str, float]]] = field(default_factory=lambda: defaultdict(list))
    shapes: Counter = field(default_factory=Counter)             # command shapes behind refusals
    errors: Counter = field(default_factory=Counter)             # (where, error) of each GUARD_ERROR

    def counts(self) -> dict:
        """What a tool result may carry: counts and percentiles, no command, path or error text."""
        return {"sessions": len(self.sessions), "lines": self.lines, "events": dict(self.events),
                "codes": {code: dict(by) for code, by in self.codes.items()}, "tools": dict(self.tools),
                "platforms": dict(self.platforms), "hook_ms": spread(self.hook_ms),
                "io_ms": spread(self.io_ms), "use_ms": spread(uses(self.traces))}


def files(folders: Iterable[Path], since: datetime) -> list[Path]:
    """Every session file in the folders from the month of since on."""
    month = since.astimezone(timezone.utc).strftime("%Y-%m")
    return sorted(path for folder in folders for path in (folder / "events").glob("*/*.jsonl")
                  if path.parent.name >= month)


def stamp(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def summarise(paths: Iterable[Path], since: datetime) -> Report:
    report = Report()
    for path in paths:
        for raw in path.read_bytes().splitlines():
            try:
                line = json.loads(raw)
                when = stamp(line["ts"])
            except (ValueError, KeyError, TypeError):
                report.unreadable += bool(raw.strip())
                continue
            if when is None or when < since:
                continue
            add(report, line, when)
    return report


def add(report: Report, line: Mapping, when: datetime) -> None:
    report.lines += 1
    report.first = when if report.first is None else min(report.first, when)
    report.last = when if report.last is None else max(report.last, when)
    report.sessions.add(line.get("session") or "")
    code, check, event = line.get("code"), line.get("check"), line.get("event") or ""
    if code:
        report.codes[code][line.get("severity") or "warning"] += 1
    if code == "GUARD_ERROR":
        report.errors[(check or line.get("tool") or "?", line.get("error") or "")] += 1
    if line.get("severity") == "refused" and line.get("cmd_head"):
        report.shapes[shape(line["cmd_head"])] += 1
    if check is not None or (code and event != TOOL_CALL):
        return
    for fix in line.get("fixed") or ():
        report.codes[fix]["fixed"] += 1
    report.events[event] += 1
    if line.get("tool"):
        report.tools[line["tool"]] += 1
    report.projects[line.get("project") or "none"] += 1
    report.platforms[line.get("platform") or "none"] += 1
    took = line.get("latency_ms")
    if isinstance(took, (int, float)):
        (report.io_ms if event == TOOL_CALL else report.hook_ms).append(float(took))
        trace = (line.get("trace") or {}).get("trace_id")
        if trace:
            report.traces[trace].append((line.get("tool") or "none", float(took)))


def shape(command: str) -> str:
    """A command's program and, when it names one, its option or subcommand: sed -i, git status."""
    words = command.split()
    if not words:
        return ""
    head = words[0].replace("\\", "/").rsplit("/", 1)[-1]
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


def shown(values: Sequence[float]) -> str:
    found = spread(values)
    if not found["n"]:
        return "none"
    return f"p50 {found['p50']:g} ms, p90 {found['p90']:g}, p99 {found['p99']:g}, max {found['max']:g} " \
           f"({found['n']:,})"


def counted(head: str, counter: Counter, limit: int | None = None) -> str:
    """head and the commonest names with their counts, as many whole ones as fit in WIDTH and no more than
    limit, then how many are left out."""
    names = [f"{name} {count:,}" for name, count in counter.most_common(limit)]
    return fitted(head, names, len(counter)) if names else f"{head} none"


def render(report: Report, days: int) -> str:
    """The report on one screen: at most about 45 lines, none wider than 110 characters, and none cut
    inside a name."""
    if not report.lines:
        return f"io-guard wrote no telemetry in the last {days} days."
    period = f"{report.first:%Y-%m-%d} to {report.last:%Y-%m-%d}"
    out = [f"io-guard, {period}: {len(report.sessions):,} sessions, {report.lines:,} lines"
           + (f", {report.unreadable:,} unreadable" if report.unreadable else ""),
           counted("Calls:", report.events), counted("Tools:", report.tools),
           counted("Projects:", report.projects), counted("Platforms:", report.platforms),
           "", f"{'Code':30}" + "".join(f"{COLUMNS[severity]:>8}" for severity in SEVERITIES)]
    ranked = sorted(report.codes.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    out += [f"{code:30}" + "".join(f"{by.get(severity, 0):>8,}" for severity in SEVERITIES)
            for code, by in ranked[:SHOWN_CODES]]
    if len(ranked) > SHOWN_CODES:
        out.append(fitted(f"and {len(ranked) - SHOWN_CODES} more codes:",
                          [code for code, _ in ranked[SHOWN_CODES:]]))
    out += ["", f"Hook call: {shown(report.hook_ms)}", f"io tool call: {shown(report.io_ms)}",
            f"One tool use, all its hooks: {shown(uses(report.traces))}"]
    if report.shapes:
        out += ["", counted("Refused most:", report.shapes, SHOWN_SHAPES)]
    if report.errors:
        out += ["", f"GUARD_ERROR, {sum(report.errors.values()):,} in all:"]
        out += [f"  {count:>5,}  {where}: {error}"[:WIDTH]
                for (where, error), count in report.errors.most_common(SHOWN_ERRORS)]
        if len(report.errors) > SHOWN_ERRORS:
            out.append(f"  and {len(report.errors) - SHOWN_ERRORS} more kinds")
    return "\n".join(out)


def fitted(head: str, names: Sequence[str], total: int | None = None) -> str:
    """head and as many whole names as fit in WIDTH, then how many of total, or of names, are left out."""
    total = len(names) if total is None else total
    for count in range(len(names), 0, -1):
        left = total - count
        line = f"{head} {', '.join(names[:count])}" + (f", and {left} more" if left else "")
        if len(line) <= WIDTH:
            return line
    return f"{head} {total:,} of them"


def run(folders: Sequence[Path], days: int, now: datetime) -> str:
    since = now - timedelta(days=days)
    return render(summarise(files(folders, since), since), days)
