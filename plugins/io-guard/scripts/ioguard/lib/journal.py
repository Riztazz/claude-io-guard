"""The edit journal: one JSONL line per write to a file, naming the file, the lines the write changed, the
tool, the time and the session's task tag, so a session's edits can be told apart by task and staged by it
(GIT-4).

A line is journal/<YYYY-MM>/<session>.jsonl in io-guard's folder. It holds no text: each line the write added
or removed is kept as the first 12 hex digits of its SHA-1, without its line ending, which is enough to find
the git hunk it landed in later, whatever lines moved around it. Only the io server writes the journal, the
PostToolUse hook for Edit and Write and the io tools for their own writes, so one lock per process keeps two
lines from interleaving.
"""
import difflib
import hashlib
import json
import logging
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ioguard.lib.context import project_root

log = logging.getLogger("ioguard.journal")

LOCK = threading.Lock()
MIDDLE_LINES = 4000          # past this many lines between the common head and tail, the middle is one change


@dataclass(frozen=True)
class Changed:
    lines: tuple[tuple[int, int], ...]    # first and last line of each change in the new text, from 1
    added: tuple[str, ...]                # the key of each line the change added
    removed: tuple[str, ...]              # the key of each line it removed


@dataclass(frozen=True)
class Entry:
    ts: datetime
    session: str
    project: str
    path: str
    tool: str
    tag: str | None
    changed: Changed


def text_of(data: bytes) -> str:
    """Bytes as text for the journal, whatever their encoding: UTF-8, with any other byte kept as it was, so
    a line read from a file and the same line read from git diff give one key."""
    return data.decode("utf-8", "surrogateescape")


def key(line: str) -> str:
    """A line's name in the journal: its SHA-1 without its line ending, shortened to 12 hex digits."""
    return hashlib.sha1(line.rstrip("\r\n").encode("utf-8", "surrogateescape")).hexdigest()[:12]


def split(text: str) -> list[str]:
    return text.splitlines()


def changed(before: str | None, after: str) -> Changed:
    """The lines after changed from before, read line by line with their endings ignored. With no before,
    the whole text is new."""
    new = split(after)
    old = [] if before is None else split(before)
    head = 0
    while head < min(len(old), len(new)) and old[head] == new[head]:
        head += 1
    tail = 0
    while tail < min(len(old), len(new)) - head and old[-1 - tail] == new[-1 - tail]:
        tail += 1
    old_mid, new_mid = old[head:len(old) - tail], new[head:len(new) - tail]
    if len(old_mid) + len(new_mid) > MIDDLE_LINES:
        spans = [("replace", 0, len(old_mid), 0, len(new_mid))] if old_mid or new_mid else []
    else:
        matcher = difflib.SequenceMatcher(None, old_mid, new_mid, autojunk=False)
        spans = [span for span in matcher.get_opcodes() if span[0] != "equal"]
    lines, added, removed = [], [], []
    for _, first_old, last_old, first_new, last_new in spans:
        start = head + first_new + 1
        lines.append((start, max(start, head + last_new)))
        added += [key(line) for line in new_mid[first_new:last_new]]
        removed += [key(line) for line in old_mid[first_old:last_old]]
    return Changed(tuple(lines), tuple(added), tuple(removed))


def within(text: str, ranges: Sequence[tuple[int, int]]) -> Changed:
    """The lines of text inside ranges, as added, for a writer that already knows where it wrote."""
    lines = split(text)
    added = [key(line) for first, last in ranges for line in lines[first - 1:last]]
    return Changed(tuple(ranges), tuple(added), ())


def file_of(home: Path, session: str, when: datetime) -> Path:
    return home / "journal" / when.strftime("%Y-%m") / f"{session}.jsonl"


def record_write(home: Path, path: Path, tool: str, before: bytes | None, after: bytes, *, when: datetime,
                 session: str, tag: str | None) -> None:
    """One journal line for a write that took path from before to after, where before is None for a new
    file. The line names the written file's own project, found from its folder as the config's is (D31), so
    a session that works in two repositories names each. A line that cannot be written is logged, and the
    write goes on."""
    if before == after:
        return
    try:
        found = changed(None if before is None else text_of(before), text_of(after))
        project = project_root(path.parent).as_posix()
        record(home, Entry(when, session, project, path.as_posix(), tool, tag, found))
    except OSError:
        log.exception("io-guard could not add the %s of %s to the journal.", tool, path)


def record(home: Path, entry: Entry) -> None:
    """Append the entry to its session's journal file."""
    line = {"ts": entry.ts.isoformat(), "session": entry.session, "project": entry.project,
            "path": entry.path, "tool": entry.tool, "tag": entry.tag,
            "lines": [list(span) for span in entry.changed.lines], "added": list(entry.changed.added),
            "removed": list(entry.changed.removed)}
    path = file_of(home, entry.session, entry.ts)
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as out:
            out.write(json.dumps(line) + "\n")


def keys_for(home: Path, tag: str, path: Path, case_insensitive: bool) -> tuple[set[str], set[str]]:
    """The keys of every line writes tagged tag added to path, and of every line they removed."""
    def name(of: str) -> str:
        return of.casefold() if case_insensitive else of
    wanted, added, removed = name(path.as_posix()), set(), set()
    for entry in entries(home):
        if entry.tag == tag and name(entry.path) == wanted:
            added.update(entry.changed.added)
            removed.update(entry.changed.removed)
    return added, removed


def entries(home: Path) -> Iterator[Entry]:
    """Every journal line in io-guard's folder, file by file, skipping a line that cannot be read."""
    for path in sorted((home / "journal").glob("*/*.jsonl")):
        for raw in path.read_text(encoding="utf-8").splitlines():
            try:
                line = json.loads(raw)
                spans = tuple((first, last) for first, last in line["lines"])
                keys = Changed(spans, tuple(line["added"]), tuple(line["removed"]))
                yield Entry(datetime.fromisoformat(line["ts"]), line["session"], line["project"],
                            line["path"], line["tool"], line["tag"], keys)
            except (ValueError, KeyError, TypeError):
                continue
