"""Hold io.run to the user's Bash and PowerShell permission rules, at the PreToolUse hook on its own call.

Claude Code's settings cannot match an MCP tool's arguments, so io.run(["git", "push"]) would otherwise run
past a Bash(git push *) rule (D14). A deny rule refuses the call with RULE_DENIED. An ask rule answers ask
with RULE_ASKED as the reason, so Claude Code shows its own permission prompt, which the desktop renders where
it declines an elicitation form (context.md, "Hooks and MCP", row 16). The check records each call it put to
the user, and io.run itself runs a command an ask rule names only when this hook asked about it, so a hook
that failed open lets none through. The rules come from every settings file Claude Code reads, as lib.rules
says.
"""
from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import Any

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import rules, runs
from ioguard.lib.context import Context, read_or_none
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Layer, Result, Severity, callable_name

RUN = callable_name("io.run")


def project_of(ctx: Context, fallback: Path) -> Path:
    """The folder whose .claude settings Claude Code reads: CLAUDE_PROJECT_DIR, else fallback."""
    named = ctx.env.get("CLAUDE_PROJECT_DIR")
    return Path(named) if named else fallback


def judge(given: Mapping[str, Any], ctx: Context, project: Path) -> rules.RuleMatch:
    """The deny or ask rule that meets the command an io.run call runs, or a match whose decision is none."""
    found = rules.load(rules.settings_files(ctx.env, project, ctx.platform), partial(read_or_none, ctx.fs))
    argv = runs.argv_of(given, ctx.probe, ctx.platform)
    return rules.RuleMatch("none", None, "") if argv is None else rules.match_argv(found, argv)


def said(found: rules.RuleMatch) -> str:
    return f"{found.command}, which the rule {found.rule.text} in {found.rule.source.as_posix()}"


class RunRules(Check):
    meta = CheckMeta(
        id="run.rules", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.OTHER}), platforms=frozenset({"win32", "darwin"}), severity=Severity.REFUSED,
        cost=Cost.MEDIUM, reads=frozenset({"argv", "lang", "code"}), writes=frozenset(), after=frozenset(),
        config={}, codes=frozenset({Code.RULE_DENIED, Code.RULE_ASKED}),
        description="Holds io.run to the user's Bash and PowerShell deny and ask rules.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.tool_name != RUN:
            return Decision.observe(self.meta.id)
        found = judge(event.tool_input, ctx, project_of(ctx, event.cwd))
        if found.decision == "deny":
            result = Result.of(Code.RULE_DENIED, f"io.run would run {said(found)} denies.", event.tool_name,
                               ctx.platform.os, evidence={"rule": found.rule.text})
            return Decision(self.meta.id, Verdict.DENY, results=(result,))
        if found.decision == "ask":
            with ctx.session.lock:
                ctx.session.asked_runs.add(runs.key(event.tool_input))
            result = Result.of(Code.RULE_ASKED, f"io.run would run {said(found)} asks about.",
                               event.tool_name, ctx.platform.os, evidence={"rule": found.rule.text})
            return Decision(self.meta.id, Verdict.ASK, results=(result,))
        return Decision.observe(self.meta.id)
