"""Hold io.run to the user's Bash and PowerShell permission rules, at the PreToolUse hook on its own call.

Claude Code's settings cannot match an MCP tool's arguments, so io.run(["git", "push"]) would otherwise run
past a Bash(git push *) rule (D14). A deny rule refuses the call with RULE_DENIED. An ask rule answers ask
with RULE_ASKED as the reason, so Claude Code shows its own permission prompt, which the desktop renders where
it declines an elicitation form (context.md, "Hooks and MCP", row 16). The check records each call it put to
the user, and io.run itself runs a command an ask rule names only when this hook asked about it, so a hook
that failed open lets none through. The rules come from every settings file Claude Code reads, as lib.rules
says. A command a shell string runs meets the rules too. A code body, or a string io-guard cannot read, asks
when it names the program of a deny or ask rule, since no rule can see what the code does.
"""
from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import runs
from ioguard.lib.context import Context, project_of
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.results import Code, Layer, Result, Severity, callable_name
from ioguard.lib.rules import RuleVerdict

RUN = callable_name("io.run")


class RunRules(Check):
    meta = CheckMeta(
        id="run.rules", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.OTHER}), platforms=EVERY_PLATFORM, severity=Severity.REFUSED,
        cost=Cost.MEDIUM, reads=frozenset({"argv", "lang", "code"}), writes=frozenset(), after=frozenset(),
        config={}, codes=frozenset({Code.RULE_DENIED, Code.RULE_ASKED}),
        description="Holds io.run to the user's Bash and PowerShell deny and ask rules.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.tool_name != RUN:
            return Decision.observe(self.meta.id)
        found = runs.judge(event.tool_input, ctx.env, ctx.fs, ctx.probe, ctx.platform,
                           project_of(ctx.env, event.cwd))
        if found.decision is RuleVerdict.DENY:
            result = Result.of(Code.RULE_DENIED, f"io.run would run {runs.said(found)}.", event.tool_name,
                               ctx.platform.os, evidence={"rule": found.rule.text})
            return Decision(self.meta.id, Verdict.DENY, results=(result,))
        if found.decision is RuleVerdict.ASK:
            ctx.session.keep_ask(event.tool_use_id, runs.key(event.tool_input), ctx.clock.now())
            rule = found.rule.text if found.rule else None
            result = Result.of(Code.RULE_ASKED, f"io.run would run {runs.said(found)}.", event.tool_name,
                               ctx.platform.os, evidence={"rule": rule})
            return Decision(self.meta.id, Verdict.ASK, results=(result,))
        return Decision.observe(self.meta.id)
