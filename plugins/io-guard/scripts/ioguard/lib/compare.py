"""What a write changed that the call did not ask for, as warnings, and the file kept before a write to
compare with.

verify.write compares each Edit and Write, shell.touched each file a command changed after the agent read it,
and the pre-commit script each staged file against its last commit. The caller decides what to compare and
what to do with the warnings.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ioguard.lib.context import FsPort, Snapshot, read_or_none
from ioguard.lib.drift import (CONTROL, NON_ASCII, REPLACEMENT, Edited, changed_lines, drift, lines,
                               lines_holding, text_of, would_collapse)
from ioguard.lib.profile import Bom, IndentKind, Profile, profile
from ioguard.lib.results import Code, Fix, Result, Severity, spec
from ioguard.lib.text import SHOWN, invisible_added, listed


@dataclass(frozen=True)
class Written:
    """One write to compare: the file before it, the file after it, and the text the call asked for."""
    path: Path
    what: str                        # the subject of each message, such as "This Edit"
    before: Profile | None           # None for a new file
    before_text: str | None          # None for a new file, or one too large to keep
    after: bytes
    expected: Edited | None          # the whole text the call asked for, when it is known
    ascii_only: bool
    allowed: frozenset[str] | None = None   # invisible characters, as U+XXXX, that pass, or None for none
    rewritten: int = 0               # lines at the top Claude Code rewrites after the write, never unasked


def ascii_kept(path: Path, listed_names: list[str]) -> bool:
    """Whether ascii_only names the file, by its extension or by its whole name, without regard to case. A
    file with no extension, such as LICENSE or .gitignore, is named by its whole name."""
    kept = {name.lower() for name in listed_names}
    return path.suffix.lower() in kept or path.name.lower() in kept


def compare(written: Written, tool: str, platform: str, collapse_percent: int) -> tuple[Result, ...]:
    """What the write changed that the call did not ask for, as warnings."""
    path, what, before, after = written.path, written.what, written.before, profile(written.after)
    name, text, subject = path.name, text_of(written.after), written.what.lower()
    changed = None if written.before_text is None else changed_lines(written.before_text, text)
    found = drift(before or profile(b""), after)
    results = []

    def add(code: Code, message: str, fix: Fix | None = None, **evidence) -> None:
        results.append(Result.of(code, message, tool, platform, file=path, evidence=evidence, fix=fix,
                                 severity=Severity.WARNING))

    def located(pattern: re.Pattern) -> tuple[int, ...]:
        """The changed lines that hold pattern, or every line that does when no changed line shows it."""
        return lines_holding(text, pattern, changed) or lines_holding(text, pattern)

    if before is not None and found.eol:
        old, new = (style.value for style in found.eol)
        add(Code.EOL_MISMATCH, f"{what} changed {name} from {old} to {new} line endings.", before=old,
            after=new, fix=Fix("Write", {}, f"Unless the task asked for {new}, write {name} back with {old} "
                                            f"line endings."))
    if before is not None and found.bom:
        change = "removed the BOM of" if found.bom[1] is Bom.NONE else "added a BOM to"
        add(Code.BOM_CHANGED, f"{what} {change} {name}.", before=found.bom[0].value, after=found.bom[1].value)
    if found.invalid:
        was, at = "was UTF-8 before and " if before is not None else "", after.encoding.first_invalid
        add(Code.ENCODING_INVALID, f"{name} {was}is not UTF-8 after {subject}, from byte {at:,}.",
            first_invalid=at)
    elif found.replacement:
        where = located(REPLACEMENT)
        add(Code.ENCODING_INVALID, f"{what} added {found.replacement:,} U+FFFD characters to {name}, on "
                                   f"{listed(where)}.", count=found.replacement, lines=list(where))
    if found.nul or found.control:
        where = located(CONTROL)
        add(Code.CONTROL_BYTES_ADDED, f"{what} added {found.nul + found.control:,} control bytes to {name}, "
                                      f"on {listed(where)}.", nul=found.nul, other=found.control,
            lines=list(where))
    if written.ascii_only and found.non_ascii:
        where = located(NON_ASCII)
        add(Code.NON_ASCII_ADDED, f"{what} added {found.non_ascii:,} non-ASCII characters to {name}, on "
                                  f"{listed(where)}.", count=found.non_ascii, lines=list(where))
    if written.allowed is not None and (before is None or written.before_text is not None):
        added = invisible_added(written.before_text or "", text, written.allowed)
        if added:
            named = ", ".join(f"[{char}] on line {line:,}" for line, char in added[:SHOWN])
            add(Code.INVISIBLE_ADDED, f"{what} added {named} to {name}, which the Read tool shows as "
                                      f"nothing.", characters=[char for _, char in added],
                fix=Fix(tool, {}, spec(Code.INVISIBLE_ADDED).fix))
    kind, now = IndentKind.NONE if before is None else before.indent.kind, after.indent.kind
    if kind in (IndentKind.TABS, IndentKind.SPACES) and now not in (kind, IndentKind.NONE):
        add(Code.INDENT_MISMATCH, f"{what} left {name} indented with {now.value}, where it used {kind.value} "
                                  f"only.", before=kind.value, after=now.value)
    if written.expected is not None:
        wanted, got = "\n".join(lines(written.expected.text)), "\n".join(lines(text))
        size = (len(wanted.encode("utf-8")), len(got.encode("utf-8")))
        unasked = tuple(number for number in changed_lines(written.expected.text, text)
                        if number not in written.expected.lines and number > written.rewritten)
        if would_collapse(*size, collapse_percent):
            add(Code.SIZE_COLLAPSED, f"{name} holds {size[1]:,} bytes after {subject}, where the call should "
                                     f"have left {size[0]:,}.", expected=size[0], actual=size[1])
        elif unasked:
            add(Code.UNINTENDED_CHANGE, f"{listed(unasked).capitalize()} of {name} differ from what "
                                        f"{subject} asked for.", lines=list(unasked))
    return tuple(results)


def write_snapshot(fs: FsPort, path: Path, tool_input: Mapping[str, Any], max_bytes: int,
                   snapshot_bytes: int) -> Snapshot:
    """The file an Edit or Write is about to change, read up to max_bytes and one more, and the input the tool
    runs with. Past snapshot_bytes only the profile is kept."""
    data = read_or_none(fs, path, max_bytes + 1)
    if data is None:
        return Snapshot(path, None, None, tool_input)
    kept = data if len(data) <= snapshot_bytes else None
    return Snapshot(path, profile(data), kept, tool_input)
