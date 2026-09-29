"""Compare each written file with the file before the write, and repair only what the write lost.

PreToolUse keeps a snapshot of the file and of the input the tool runs with, after conform.write and
conform.edit. PostToolUse reads the file again and compares. A BOM the write dropped, and a single ending
style it changed, are data that conform did not keep, such as a Write with conform.write off, and are put
back while repair is on. The harness records a file as its own write left it, so every repair tells the
agent to read the file before the next Edit. The rest is reported and left as it is: bytes that stop being
UTF-8 or gain U+FFFD, new control bytes, non-ASCII in a file the project keeps ASCII, a new character the
Read tool shows as nothing, such as the U+FEFF a JSON escape in the call turns into, a new indent style, a
file far smaller than the call should have left, and lines outside the edit that differ from what the call
asked for. A note of Claude Code's memory leaves its frontmatter out of that last comparison, because the
desktop app rewrites it after every write. The pre-commit script runs the same comparison on the staged diff.
A file the agent has read keeps its new profile in the session, so shell.touched blames a later shell command
only for what that command did.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context, Snapshot, memory_file, read_or_none
from ioguard.lib.locks import file_lock, lock_folder
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.drift import (CONTROL, NON_ASCII, REPLACEMENT, Edited, changed_lines, drift, edited,
                               frontmatter_end, lines, lines_holding, restored, text_of, would_collapse)
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.profile import Bom, IndentKind, Profile, profile
from ioguard.lib.results import Code, Fix, Layer, Result, Severity, spec
from ioguard.lib.text import invisible_added

SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_BYTES = 16 * 1024 * 1024
REREAD = "Read the file again before the next Edit, because io-guard changed it after the write."
SHOWN = 5               # line numbers a message lists before it gives the rest as a count
REPAIR_WAIT_S = 2.0     # seconds the repair waits for an io tool that holds the file, before it gives up


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
    allowed: frozenset[str] | None = None   # invisible characters, as U+XXXX, that pass; None checks none
    rewritten: int = 0               # lines at the top Claude Code rewrites after the write, never unasked


def ascii_kept(path: Path, listed_names: list[str]) -> bool:
    """Whether ascii_only names the file, by its extension or by its whole name, without regard to case. A
    file with no extension, such as LICENSE or .gitignore, is named by its whole name."""
    kept = {name.lower() for name in listed_names}
    return path.suffix.lower() in kept or path.name.lower() in kept


def listed(numbers: tuple[int, ...]) -> str:
    """Line numbers for a message: "line 4", "lines 4 and 9", "lines 1, 2, 3, 4, 5 and 7 more"."""
    shown = [f"{number:,}" for number in numbers[:SHOWN]]
    if not shown:
        return "no line"
    if len(numbers) > SHOWN:
        return f"lines {', '.join(shown)} and {len(numbers) - SHOWN:,} more"
    if len(shown) == 1:
        return f"line {shown[0]}"
    return f"lines {', '.join(shown[:-1])} and {shown[-1]}"


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


def write_snapshot(event: Event, ctx: Context, options: Mapping[str, Any]) -> Snapshot:
    """The file an Edit or Write is about to change, and the input the tool runs with. verify.write keeps
    it, and journal.write keeps it when verify.write is off. Past snapshot_bytes only the profile is kept."""
    path = event.file_path
    data = read_or_none(ctx.fs, path, options["max_bytes"] + 1)
    if data is None:
        return Snapshot(path, None, None, event.tool_input)
    kept = data if len(data) <= options["snapshot_bytes"] else None
    return Snapshot(path, profile(data), kept, event.tool_input)


class VerifyWrite(Check):
    meta = CheckMeta(
        id="verify.write", layer=Layer.BYTES,
        events=frozenset({HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.WARNING, cost=Cost.MEDIUM,
        reads=frozenset({"file_path", "content", "old_string", "new_string", "replace_all"}),
        writes=frozenset(), after=frozenset({"conform.write", "conform.edit", "journal.write"}),
        config={
            "repair": ConfigKey(bool, True, "Put back a BOM a write dropped and the line endings it "
                                "changed."),
            "ascii_only": ConfigKey(list, [], "File extensions, such as .py, or whole file names, such as "
                                    "LICENSE, where a write that adds non-ASCII characters gets a warning. A "
                                    "project's list replaces it."),
            "collapse_percent": ConfigKey(int, 50, "A file left with less than this percent of the bytes the "
                                          "call should have left gets a warning."),
            "snapshot_bytes": ConfigKey(int, SNAPSHOT_BYTES, "The largest file, in bytes, whose text is kept "
                                        "before a write, for the line comparison."),
            "max_bytes": ConfigKey(int, MAX_BYTES, "The largest file, in bytes, that is compared at all."),
        },
        codes=frozenset({Code.EOL_CONVERTED, Code.BOM_RESTORED, Code.EOL_MISMATCH, Code.BOM_CHANGED,
                         Code.ENCODING_INVALID, Code.CONTROL_BYTES_ADDED, Code.NON_ASCII_ADDED,
                         Code.INVISIBLE_ADDED,
                         Code.INDENT_MISMATCH, Code.SIZE_COLLAPSED, Code.UNINTENDED_CHANGE}),
        description="Compares each written file with the file before the write, and puts back a lost BOM "
                    "or line endings.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.file_path is None or event.tool_use_id is None:
            return Decision.observe(self.meta.id)
        if event.kind is HookEvent.PRE_TOOL_USE:
            ctx.session.keep_snapshot(event.tool_use_id, write_snapshot(event, ctx, self.options))
            return Decision.observe(self.meta.id)
        snapshot = ctx.session.take_snapshot(event.tool_use_id)
        if event.kind is not HookEvent.POST_TOOL_USE or not isinstance(snapshot, Snapshot):
            return Decision.observe(self.meta.id)
        try:
            data = ctx.fs.read_bytes(snapshot.path, self.options["max_bytes"] + 1)
        except OSError:
            return Decision.observe(self.meta.id)
        before = snapshot.profile
        if len(data) > self.options["max_bytes"] or (before or profile(data)).binary:
            return Decision.observe(self.meta.id)
        repaired = self.repair(snapshot, data, event, ctx)
        if repaired is not None:
            data = repaired[1]
        with ctx.session.lock:
            if snapshot.path in ctx.session.read_profiles:
                ctx.session.read_profiles[snapshot.path] = profile(data)
        rewritten = frontmatter_end(text_of(data)) if memory_file(snapshot.path, ctx.env) else 0
        kept = ascii_kept(snapshot.path, self.options["ascii_only"])
        written = Written(snapshot.path, f"This {event.tool_name}", before,
                          None if snapshot.data is None else text_of(snapshot.data), data,
                          self.expected(snapshot, event), kept,
                          frozenset(ctx.config.get("invisible_allowed")), rewritten)
        found = (() if repaired is None else (repaired[0],)) + \
            compare(written, event.tool_name, ctx.platform.os, self.options["collapse_percent"])
        if not found:
            return Decision.observe(self.meta.id)
        return Decision(self.meta.id, Verdict.ALLOW, results=found)

    @staticmethod
    def expected(snapshot: Snapshot, event: Event) -> Edited | None:
        """The whole text the call asked for, and the lines of it the tool may restyle, such as its quotes:
        none for a Write, whose content lands byte-exact, and new_string's lines for an Edit."""
        given = snapshot.tool_input
        if event.tool is Tool.WRITE:
            content = given.get("content")
            return Edited(content, frozenset()) if isinstance(content, str) else None
        old, new = given.get("old_string"), given.get("new_string")
        if snapshot.data is None or not isinstance(old, str) or not isinstance(new, str):
            return None
        return edited(text_of(snapshot.data), old, new, given.get("replace_all") is True)

    def repair(self, snapshot: Snapshot, data: bytes, event: Event,
               ctx: Context) -> tuple[Result, bytes] | None:
        """Put back a lost BOM and a changed ending style, and say so. None when nothing was put back."""
        before, after = snapshot.profile, profile(data)
        if before is None or not self.options["repair"]:
            return None
        found = drift(before, after)
        bom_lost = found.bom == (Bom.UTF8, Bom.NONE)
        if not found.eol and not bom_lost:
            return None
        fixed = restored(data, before.eol if found.eol else None, Bom.UTF8 if bom_lost else after.bom)
        if fixed is None or fixed == data:
            return None
        try:
            with file_lock(snapshot.path, lock_folder(ctx.data_dir), REPAIR_WAIT_S):
                if read_or_none(ctx.fs, snapshot.path, len(data) + 1) != data:
                    return None
                ctx.fs.write_atomic(snapshot.path, fixed)
        except TimeoutError:
            return None
        lost = ([f"{after.eol.value} line endings where it had {before.eol.value}"] if found.eol else []) + \
               (["no BOM"] if bom_lost else [])
        message = (f"The {event.tool_name} tool left {snapshot.path.name} with {' and '.join(lost)}, so "
                   f"io-guard wrote back what the file had.")
        code = Code.EOL_CONVERTED if found.eol else Code.BOM_RESTORED
        return Result.of(code, message, event.tool_name, ctx.platform.os, file=snapshot.path,
                         fix=Fix("Read", {"file_path": str(snapshot.path)}, REREAD)), fixed
