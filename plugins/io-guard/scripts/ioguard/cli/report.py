"""The report of what io-guard fixed, warned about and refused, printed on one screen.

lib.telemetry_summary sums the telemetry, and this prints it. The printed report holds command shapes and
error hashes, so it goes to a terminal only. With --html it writes the dashboard page's stats into one file
instead, which opens in any browser.
"""
import json
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from ioguard.lib.telemetry_summary import SEVERITIES, Summary, files, page, spread, summarise, uses

COLUMNS = {"fixed": "fixed", "warning": "warned", "refused": "refused", "info": "info"}
SHOWN_CODES = 12
SHOWN_SHAPES = 5
SHOWN_ERRORS = 8
WIDTH = 110
PAGE = Path(__file__).resolve().parents[3] / "ui" / "dashboard.html"
STATIC_MARK = "<!-- io-guard static data -->"


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


def render(summary: Summary, days: int) -> str:
    """The report on one screen: at most about 45 lines, none wider than 110 characters, and none cut
    inside a name."""
    if not summary.lines:
        return f"io-guard wrote no telemetry in the last {days} days."
    period = f"{summary.first:%Y-%m-%d} to {summary.last:%Y-%m-%d}"
    out = [f"io-guard, {period}: {len(summary.sessions):,} sessions, {summary.lines:,} lines"
           + (f", {summary.unreadable:,} unreadable" if summary.unreadable else ""),
           counted("Calls:", summary.events), counted("Tools:", summary.tools),
           counted("Projects:", summary.projects), counted("Platforms:", summary.platforms),
           "", f"{'Code':30}" + "".join(f"{COLUMNS[severity]:>8}" for severity in SEVERITIES)]
    ranked = sorted(summary.codes.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    out += [f"{code:30}" + "".join(f"{by.get(severity, 0):>8,}" for severity in SEVERITIES)
            for code, by in ranked[:SHOWN_CODES]]
    if len(ranked) > SHOWN_CODES:
        out.append(fitted(f"and {len(ranked) - SHOWN_CODES} more codes:",
                          [code for code, _ in ranked[SHOWN_CODES:]]))
    out += ["", f"Hook call: {shown(summary.hook_ms)}", f"io tool call: {shown(summary.io_ms)}",
            f"io.run, the program's own time: {shown(summary.run_ms)}",
            f"One tool use, all its hooks: {shown(uses(summary.traces))}"]
    if summary.shapes:
        out += ["", counted("Refused most:", summary.shapes, SHOWN_SHAPES)]
    if summary.errors:
        out += ["", f"GUARD_ERROR, {sum(summary.errors.values()):,} in all:"]
        out += [f"  {count:>5,}  {where}: {error}"[:WIDTH]
                for (where, error), count in summary.errors.most_common(SHOWN_ERRORS)]
        if len(summary.errors) > SHOWN_ERRORS:
            out.append(f"  and {len(summary.errors) - SHOWN_ERRORS} more kinds")
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


def static_page(folders: Sequence[Path], days: int, now: datetime) -> bytes:
    """The dashboard page with the stats of every project written into it, so it opens as a file. It shows
    the stats alone, since a file has no server to change a setting through."""
    inline = json.dumps(page(folders, days, now), ensure_ascii=True).replace("</", "<\\/")
    template = PAGE.read_bytes().decode("utf-8")
    inlined = template.replace(STATIC_MARK, f"<script>window.IOGUARD_STATIC = {inline};</script>")
    return inlined.encode("ascii")
