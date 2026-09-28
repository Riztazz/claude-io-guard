"""Task 31's measurement: the baseline's failure classes counted over two periods of transcripts, before
io-guard and after it, per 1,000 recorded calls, beside each target.

Both periods are counted by the same rules, from the labels the corpus puts on each call (cli.labels), with
each tool use id counted once (cli.corpus.records). The baseline of 2026-09-27 counted a few classes by other
means, such as the scratchpad scripts on disk, so its numbers stand beside the result as a reference and never
as the comparison. The guard's own time comes from its telemetry, through cli.report.
"""
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime

from ioguard.cli.corpus import Record

ADOPTED = "2026-09-28"               # task 30 turned io-guard on in the lead's projects
SHELLS = frozenset({"Bash", "PowerShell"})
WRITERS = frozenset({"Edit", "MultiEdit", "Write"})
SCRIPT = re.compile(r"scratchpad/[^/]+\.(?:py|ps1|sh|js)$", re.I)
WRITES_A_FILE = re.compile(r"open\([^)]*['\"][wax]b?\+?['\"]|\.write_(?:text|bytes)\(|Set-Content|Add-Content|"
                           r"Out-File|WriteAll(?:Text|Lines|Bytes)|>\s*\"?\$|shutil\.(?:copy|move)")


@dataclass(frozen=True)
class Measure:
    name: str
    target: str
    reference: str                   # the baseline of 2026-09-27, as its own count said it
    counts: Callable[[Record], str | None]   # what the record counts as, or None when it does not count
    most_lower: float | None         # the share it must drop by, or None when the target is none at all


def flagged(*labels: str, tools: frozenset[str]) -> Callable[[Record], str | None]:
    """A record of one of tools with any of labels counts once, by its tool use id."""
    return lambda record: record.id if record.tool in tools and set(labels) & set(record.labels) else None


def scratch_writer(record: Record) -> str | None:
    """A Write that makes a scratchpad script whose text writes a file counts once per script path, so a
    script written again is still one script."""
    path = str(record.input.get("file_path") or "").replace("\\", "/")
    text = str(record.input.get("content") or "")
    return path.lower() if record.tool == "Write" and SCRIPT.search(path) and WRITES_A_FILE.search(text) else None


MEASURES = (
    Measure("Bash commands failing in transport", "none", "122",
            flagged("unexpected-eof", "heredoc-eof", tools=SHELLS), None),
    Measure("Edit anchor misses", "at least 50% lower", "67", flagged("not-found", tools=WRITERS), 0.5),
    Measure("Not-read-yet errors", "at least 50% lower", "82", flagged("not-read-yet", tools=WRITERS), 0.5),
    Measure("Modified-since-read errors", "at least 50% lower", "30",
            flagged("modified-since-read", tools=WRITERS), 0.5),
    Measure("Git LF and CRLF warnings", "none", "328", flagged("git-eol", tools=SHELLS), None),
    Measure("New scratchpad scripts that write files", "at least 80% lower", "417 on disk", scratch_writer, 0.8),
)
FEWEST_CALLS = 1_000                 # a period with fewer calls gives no verdict


@dataclass
class Period:
    first: str
    last: str
    calls: int = 0
    found: dict[str, set[str]] = field(default_factory=dict)

    def count(self, name: str) -> int:
        return len(self.found.get(name, ()))

    def rate(self, name: str) -> float:
        """Per 1,000 calls."""
        return 1000 * self.count(name) / self.calls if self.calls else 0.0


def when(record: Record) -> str:
    """The record's day, as YYYY-MM-DD, or empty when it has no time."""
    return record.ts[:10]


def measure(records: Iterable[Record], since: str) -> tuple[Period, Period]:
    """The calls before since and from since on, each with its count of every measure."""
    before, after = Period(first="", last=""), Period(first="", last="")
    for record in records:
        day = when(record)
        if not day:
            continue
        period = after if day >= since else before
        period.first = min(period.first or day, day)
        period.last = max(period.last, day)
        period.calls += 1
        for each in MEASURES:
            key = each.counts(record)
            if key is not None:
                period.found.setdefault(each.name, set()).add(key)
    return before, after


def verdict(each: Measure, before: Period, after: Period) -> str:
    if after.calls < FEWEST_CALLS:
        return "too few calls"
    old, new = before.rate(each.name), after.rate(each.name)
    if each.most_lower is None:
        return "met" if new == 0 else "not met"
    if old == 0:
        return "met" if new == 0 else "not met"
    return "met" if new <= old * (1 - each.most_lower) else "not met"


def render(before: Period, after: Period, hook_p95: float | None) -> str:
    """The table: each measure per 1,000 calls before and after, its target, and whether the target holds."""
    out = [f"Before io-guard: {before.calls:,} calls, {before.first} to {before.last}. "
           f"After: {after.calls:,} calls, {after.first or '-'} to {after.last or '-'}.",
           "", f"{'Measure':44}{'before':>9}{'after':>9}  {'target':22}{'result':14}reference"]
    for each in MEASURES:
        out.append(f"{each.name:44}{before.rate(each.name):>9.2f}{after.rate(each.name):>9.2f}  "
                   f"{each.target:22}{verdict(each, before, after):14}{each.reference}")
    latency = "none" if hook_p95 is None else f"{hook_p95:g} ms"
    held = "no calls yet" if hook_p95 is None else ("met" if hook_p95 <= 300 else "not met")
    target = "within 300 ms (D16)"
    out.append(f"{'Hook latency p95':44}{'-':>9}{latency:>9}  {target:22}{held:14}not measured")
    out.append("")
    out.append(f"Rates are per 1,000 recorded calls, each tool use counted once, and each scratchpad script "
               f"once by its path. A period of fewer than {FEWEST_CALLS:,} calls gives no verdict.")
    return "\n".join(out)


def since_date(text: str) -> str:
    """text as YYYY-MM-DD. ValueError when it is not a date."""
    return datetime.strptime(text, "%Y-%m-%d").strftime("%Y-%m-%d")
