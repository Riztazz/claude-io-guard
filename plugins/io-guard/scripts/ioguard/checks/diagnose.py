"""Answer a failed file call with where the text really is, the paths that exist, or the parts that fit.

Two routes reach one diagnosis, lib.diagnosis. A Read, Grep or Glob that fails while it runs fires
PostToolUseFailure, and diagnose.failure answers there. An Edit or Write that Claude Code rejects before it
runs fires no hook at all (context.md, "Hooks and MCP", row 30), so diagnose.refused finds the refusal at the
end of the transcript at the session's next hook, and answers once per refused call, before the model tries
again. A lock is write.locks' to name.
"""
import logging
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import paths, transcript
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context, claude_folder
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.diagnosis import FIND_LIMIT, PART_BYTES, Diagnosis, Failed
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Layer, Result, Severity

log = logging.getLogger("ioguard.checks.diagnose")

TAIL_BYTES = 256 * 1024
OPTIONS = {"find_limit": ConfigKey(int, FIND_LIMIT, "The most folder entries a search for a missing file's "
                                   "name walks."),
           "part_bytes": ConfigKey(int, PART_BYTES, "The bytes of one Read part io-guard suggests for a file "
                                   "too large to read whole.")}


def decided(check_id: str, found: tuple[Result, ...]) -> Decision:
    return Decision(check_id, Verdict.ALLOW, results=found) if found else Decision.observe(check_id)


class DiagnoseFailure(Check):
    meta = CheckMeta(
        id="diagnose.failure", layer=Layer.READ, events=frozenset({HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset({Tool.READ, Tool.GREP, Tool.GLOB, Tool.EDIT, Tool.WRITE}),
        platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING, cost=Cost.MEDIUM,
        reads=frozenset({"file_path", "path", "pattern", "old_string"}), writes=frozenset(),
        after=frozenset(), config=OPTIONS,
        codes=frozenset({Code.PATH_NOT_FOUND, Code.READ_TOO_LARGE, Code.PATTERN_INVALID,
                         Code.SEARCH_TOO_BROAD, Code.ANCHOR_NOT_FOUND, Code.ANCHOR_AMBIGUOUS,
                         Code.STALE_VIEW}),
        description="Answers a failed Read, Grep, Glob, Edit or Write with the path, the part or the pattern "
                    "that works.")

    def run(self, event: Event, ctx: Context) -> Decision:
        failed = Failed(event.tool_name, event.tool_input, event.error or "", event.cwd)
        return decided(self.meta.id, Diagnosis(failed, ctx.fs, ctx.git, ctx.platform, self.options).results())


class DiagnoseRefused(Check):
    meta = CheckMeta(
        id="diagnose.refused", layer=Layer.STALE,
        events=frozenset({HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset(), platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING,
        cost=Cost.MEDIUM, reads=frozenset(), writes=frozenset(), after=frozenset(),
        config={**OPTIONS,
                "tail_bytes": ConfigKey(int, TAIL_BYTES, "The bytes at the end of the transcript read for "
                                        "calls Claude Code refused before any hook ran.")},
        codes=frozenset({Code.PATH_NOT_FOUND, Code.ANCHOR_NOT_FOUND, Code.ANCHOR_AMBIGUOUS, Code.STALE_VIEW}),
        description="Answers an Edit or Write that Claude Code refused before any hook ran, at the next "
                    "hook.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.transcript is None:
            return Decision.observe(self.meta.id)
        projects = paths.normalise(str(claude_folder(ctx.env) / "projects"), event.cwd, ctx.platform)
        if paths.inside(paths.normalise(str(event.transcript), event.cwd, ctx.platform), [projects],
                        ctx.platform) is None:
            log.debug("io-guard left %s unread: it is not under %s", event.transcript, projects)
            return Decision.observe(self.meta.id)
        try:
            tail = ctx.fs.read_tail(event.transcript, self.options["tail_bytes"])
        except OSError:
            return Decision.observe(self.meta.id)
        if b"<tool_use_error>" not in tail:
            return Decision.observe(self.meta.id)
        found: list[Result] = []
        for refusal in transcript.refusals(tail):
            if not ctx.session.first_time(f"refused:{refusal.tool_use_id}"):
                continue
            cwd = Path(refusal.cwd) if refusal.cwd else event.cwd
            failed = Failed(refusal.tool, refusal.tool_input, refusal.error, cwd)
            found.extend(Diagnosis(failed, ctx.fs, ctx.git, ctx.platform, self.options).results())
        return decided(self.meta.id, tuple(found))
