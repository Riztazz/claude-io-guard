"""Record every write in the edit journal: the file, the lines it changed, the tool, the time and the
session's task tag, the last one io.snapshot named (GIT-4).

The check reads an Edit's or a Write's file at PostToolUse against the snapshot verify.write kept at
PreToolUse, before verify.write takes it, and the io tools call record_write from mcp.in_place for their own
writes. A file too large for verify.write to keep its bytes goes unrecorded, since there is nothing to compare
it with. A journal line that cannot be written is logged, and the call goes on.
"""
import logging
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import journal
from ioguard.lib.context import Context, Snapshot, read_or_none
from ioguard.lib.decisions import Decision
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Layer, Severity

log = logging.getLogger("ioguard.journal")


def enabled(ctx: Context) -> bool:
    return ctx.data_dir is not None and ctx.config.check_options("journal.write").get("enabled", True)


def record_write(ctx: Context, path: Path, tool: str, before: bytes | None, after: bytes) -> None:
    """One journal line for a write that took path from before to after, where before is None for a new
    file."""
    if not enabled(ctx) or before == after:
        return
    try:
        changed = journal.changed(None if before is None else journal.text_of(before), journal.text_of(after))
        project = ctx.env.get("CLAUDE_PROJECT_DIR") or ""
        entry = journal.Entry(ctx.clock.now(), ctx.session.session_id or "unknown", project, path.as_posix(),
                              tool, ctx.session.tag, changed)
        journal.record(ctx.data_dir, entry)
    except OSError:
        log.exception("io-guard could not add the %s of %s to the journal.", tool, path)


class JournalWrite(Check):
    meta = CheckMeta(
        id="journal.write", layer=Layer.BYTES, events=frozenset({HookEvent.POST_TOOL_USE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.INFO, cost=Cost.MEDIUM, reads=frozenset({"file_path"}), writes=frozenset(),
        after=frozenset(), config={}, codes=frozenset(),
        description="Records each Edit and Write in the edit journal, with the lines it changed and the "
                    "session's task tag.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.tool_use_id is None or not enabled(ctx):
            return Decision.observe(self.meta.id)
        kept = ctx.session.peek_snapshot(event.tool_use_id)
        if not isinstance(kept, Snapshot) or (kept.profile is not None and kept.data is None):
            return Decision.observe(self.meta.id)
        after = read_or_none(ctx.fs, kept.path)
        if after is not None:
            record_write(ctx, kept.path, event.tool_name, kept.data, after)
        return Decision.observe(self.meta.id)
