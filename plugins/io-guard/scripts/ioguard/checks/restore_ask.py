"""Put io.restore to the user when it would replace files that changed since their snapshot, at the PreToolUse
hook on its own call.

A restore writes a file back to the bytes it held before a task, so every edit made to it since is lost. The
check answers ask with RESTORE_ASKED, naming the files, so Claude Code shows its own permission prompt, which
the desktop renders where it declines an elicitation form (context.md, "Hooks and MCP", row 16). It records
each restore it put to the user, and io.restore writes only a restore this hook asked about, so a hook that
failed open lets none through.
"""
from functools import partial

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.checks.run_rules import project_of
from ioguard.lib import paths, snapshots
from ioguard.lib.context import Context, read_or_none
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Layer, Result, Severity, callable_name

RESTORE = callable_name("io.restore")
NAMED = 10


class RestoreAsk(Check):
    meta = CheckMeta(
        id="restore.ask", layer=Layer.LOCATION, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.OTHER}), platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING,
        cost=Cost.MEDIUM, reads=frozenset({"tag", "paths"}), writes=frozenset(), after=frozenset(),
        config={}, codes=frozenset({Code.RESTORE_ASKED}),
        description="Asks the user before io.restore replaces files that changed since their snapshot.")

    def run(self, event: Event, ctx: Context) -> Decision:
        given = event.tool_input
        if event.tool_name != RESTORE or ctx.data_dir is None or not isinstance(given.get("tag"), str):
            return Decision.observe(self.meta.id)
        project = project_of(ctx, event.cwd)
        found = snapshots.find(ctx.data_dir, given["tag"], project, ctx.clock.now())
        if found is None:
            return Decision.observe(self.meta.id)
        raw = given.get("paths") or []
        wanted = [paths.normalise(each, project, ctx.platform) for each in raw
                  if isinstance(each, str)] or None
        plan = snapshots.pending(found, wanted, partial(read_or_none, ctx.fs), ctx.platform.case_insensitive)
        if not plan.changed:
            return Decision.observe(self.meta.id)
        with ctx.session.lock:
            ctx.session.asked_restores.add(plan.key())
        names = ", ".join(kept.path.name for kept in plan.changed[:NAMED])
        more = f" and {len(plan.changed) - NAMED:,} more" if len(plan.changed) > NAMED else ""
        result = Result.of(Code.RESTORE_ASKED, f"io.restore would write {len(plan.changed):,} files back as "
                           f"snapshot {found.tag} kept them, losing every edit since: {names}{more}.",
                           event.tool_name, ctx.platform.os)
        return Decision(self.meta.id, Verdict.ASK, results=(result,))
