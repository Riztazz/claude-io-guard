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
from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib.compare import Written, ascii_kept, compare, write_snapshot
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.drift import Edited, drift, edited, frontmatter_end, restored, text_of
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.folders import memory_file
from ioguard.lib.locks import file_lock, lock_folder
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.ports import read_or_none
from ioguard.lib.profile import Bom, profile
from ioguard.lib.results import Code, Fix, Layer, Result, Severity
from ioguard.lib.session import Snapshot

SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_BYTES = 16 * 1024 * 1024
REREAD = "Read the file again before the next Edit, because io-guard changed it after the write."
REPAIR_WAIT_S = 2.0     # seconds the repair waits for an io tool that holds the file, before it gives up


class VerifyWrite(Check):
    meta = CheckMeta(
        id="verify.write", layer=Layer.BYTES,
        events=frozenset({HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=EVERY_PLATFORM,
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
            snapshot = write_snapshot(ctx.fs, event.file_path, event.tool_input, self.options["max_bytes"],
                                      self.options["snapshot_bytes"])
            ctx.session.keep_snapshot(event.tool_use_id, snapshot)
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
