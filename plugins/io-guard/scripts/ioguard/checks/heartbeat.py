"""Tell the user once, at the start of a turn, that the io server is not running, so tool calls go unchecked.

Claude Code restarts a server that exited on the next hook call, and one that cannot start leaves every hook
failing open with nothing said to the model (context.md, "Hooks and MCP", row 18). So a command hook on
UserPromptSubmit, which needs no server, reads the heartbeat the server keeps. A beat older than stale_s with
no clean stop means the server died and the calls since then ran unchecked. With no heartbeat at all, the
server never started this session, and Claude Code's own cache says when it gave up on it: a plugin server
that failed to start is skipped in every session for 15 minutes (row 33).
"""
from datetime import datetime
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import heartbeat
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context, session_file
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent
from ioguard.lib.results import Code, Fix, Layer, Result, Severity, render

SERVER = "plugin:io-guard:io"
SKIP_S = 900        # how long Claude Code skips a plugin server that failed, when its cache names no ttlMs


def clock(moment: datetime) -> str:
    return moment.astimezone().strftime("%H:%M:%S")


class Heartbeat(Check):
    meta = CheckMeta(
        id="server.heartbeat", layer=Layer.INTERNAL, events=frozenset({HookEvent.USER_PROMPT_SUBMIT}),
        tools=frozenset(), platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING,
        cost=Cost.CHEAP, reads=frozenset(), writes=frozenset(), after=frozenset(),
        config={"stale_s": ConfigKey(int, 30, "Seconds after its last heartbeat that the io server counts as "
                                     "stopped. It writes one every 5 seconds.")},
        codes=frozenset({Code.SERVER_DOWN}),
        description="Warns once at the start of a turn when the io server is not running.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if ctx.data_dir is None:
            return Decision.observe(self.meta.id)
        try:
            beat = heartbeat.parse(ctx.fs.read_bytes(session_file(ctx.data_dir, event.session_id, "alive")))
        except OSError:
            return self.skipped(event, ctx)
        if beat is None or beat.stopped is not None:
            return Decision.observe(self.meta.id)
        age = (ctx.clock.now() - beat.beat).total_seconds()
        key = f"server-down:{beat.pid}:{beat.beat.isoformat()}"
        if age <= self.options["stale_s"] or not ctx.session.first_time(key):
            return Decision.observe(self.meta.id)
        return self.warn(event, ctx, f"io-guard's io server last answered at {clock(beat.beat)}, so the "
                                     f"tool calls since then ran without its checks.", None,
                         {"pid": beat.pid, "age_s": round(age)})

    def skipped(self, event: Event, ctx: Context) -> Decision:
        """The server never wrote a heartbeat this session. Claude Code's cache says whether it skipped it."""
        folder = claude_folder(ctx)
        try:
            cache = ctx.fs.read_bytes(folder / "mcp-needs-auth-cache.json") if folder else b""
        except OSError:
            return Decision.observe(self.meta.id)
        found = heartbeat.skipped_since(cache, SERVER, SKIP_S)
        if found is None or not found[0] <= ctx.clock.now() < found[1] \
                or not ctx.session.first_time(f"skipped:{found[0]}"):
            return Decision.observe(self.meta.id)
        failed, retried = found
        fix = Fix("/mcp", {}, "Run /mcp to see why it failed and to reconnect it.")
        return self.warn(event, ctx, f"Claude Code did not start io-guard's io server this session, because "
                                     f"it failed to start at {clock(failed)}, so no tool call is checked "
                                     f"before {clock(retried)}.", fix, {"failed": failed.isoformat()})

    def warn(self, event: Event, ctx: Context, message: str, fix: Fix | None, evidence: dict) -> Decision:
        result = Result.of(Code.SERVER_DOWN, message, event.tool_name or "UserPromptSubmit", ctx.platform.os,
                           fix=fix, evidence=evidence)
        return Decision(self.meta.id, Verdict.ALLOW, results=(result,), user_message=render(result))


def claude_folder(ctx: Context) -> Path | None:
    """Claude Code's own folder: CLAUDE_CONFIG_DIR, or .claude in the user's home. None with neither."""
    named = ctx.env.get("CLAUDE_CONFIG_DIR")
    home = ctx.env.get("USERPROFILE") or ctx.env.get("HOME")
    if named:
        return Path(named)
    return Path(home) / ".claude" if home else None
