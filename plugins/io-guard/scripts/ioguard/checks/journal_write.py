"""Record every write in the edit journal: the file, the lines it changed, the tool, the time and the
session's task tag, the last one io.snapshot named (GIT-4).

The check reads an Edit's or a Write's file at PostToolUse against the snapshot verify.write kept at
PreToolUse, before verify.write takes it. With verify.write off, the check keeps that snapshot itself, after
conform.write and conform.edit, and takes it when it is done. The io tools record their own writes from
mcp.in_place. A file too large to keep its bytes goes unrecorded, since there is nothing to compare it with.
A journal line that cannot be written is logged, and the call goes on.
"""
from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import journal
from ioguard.lib.compare import write_snapshot
from ioguard.lib.context import Context, Snapshot, read_or_none
from ioguard.lib.decisions import Decision
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Layer, Severity


class JournalWrite(Check):
    meta = CheckMeta(
        id="journal.write", layer=Layer.BYTES,
        events=frozenset({HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.INFO, cost=Cost.MEDIUM, reads=frozenset({"file_path"}), writes=frozenset(),
        after=frozenset({"conform.write", "conform.edit"}), config={}, codes=frozenset(),
        description="Records each Edit and Write in the edit journal, with the lines it changed and the "
                    "session's task tag.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.tool_use_id is None or event.file_path is None or ctx.data_dir is None:
            return Decision.observe(self.meta.id)
        verify = ctx.config.check_options("verify.write")
        alone = not verify.get("enabled", True)
        if event.kind is HookEvent.PRE_TOOL_USE:
            if alone:
                snapshot = write_snapshot(ctx.fs, event.file_path, event.tool_input, verify["max_bytes"],
                                          verify["snapshot_bytes"])
                ctx.session.keep_snapshot(event.tool_use_id, snapshot)
            return Decision.observe(self.meta.id)
        kept = (ctx.session.take_snapshot if alone else ctx.session.peek_snapshot)(event.tool_use_id)
        if not isinstance(kept, Snapshot) or (kept.profile is not None and kept.data is None):
            return Decision.observe(self.meta.id)
        after = read_or_none(ctx.fs, kept.path)
        if after is not None:
            journal.record_write(ctx.data_dir, kept.path, event.tool_name, kept.data, after,
                                 when=ctx.clock.now(), session=ctx.session.session_id or "unknown",
                                 tag=ctx.session.tag)
        return Decision.observe(self.meta.id)
