"""Put a command io-guard would start to the user, at the PreToolUse hook on the call that would let it run.

A project's .claude/io-guard.json may name verify and format commands, which io-guard starts (lib.trust). On
io.trust the check answers ask with TRUST_ASKED, listing each command, so Claude Code shows its own permission
prompt, the one control the model cannot answer for the user. The prompt says when a command runs a file from
inside the project, since a pull can change that file and leave the command as it was. On io.config it answers
ask with CONFIG_ASKED for a write of a key marked runs into the user's own file, which reaches every project.
Each ask is recorded under the call's tool use id, and the tool acts only on the ask its own hook recorded, so
a hook that failed open approves nothing.
"""
import json

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import config_edit, trust, waiting
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.results import Code, Layer, Result, Severity, callable_name
from ioguard.lib.text import quoted

TRUST = callable_name("io.trust")
CONFIG = callable_name("io.config")


class TrustAsk(Check):
    meta = CheckMeta(
        id="trust.ask", layer=Layer.INTERNAL, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.OTHER}), platforms=EVERY_PLATFORM, severity=Severity.WARNING,
        cost=Cost.CHEAP, reads=frozenset(), writes=frozenset(), after=frozenset(), config={},
        codes=frozenset({Code.TRUST_ASKED, Code.CONFIG_ASKED}),
        description="Asks the user before io.trust approves a project's commands, or io.config writes a "
                    "command or a variable.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.tool_name == CONFIG:
            return self.config(event, ctx)
        if event.tool_name != TRUST or not ctx.held or ctx.project is None:
            return Decision.observe(self.meta.id)
        ctx.session.keep_ask(event.tool_use_id, trust.fingerprint(ctx.held), ctx.clock.now())
        scripts = waiting.inside(ctx.held, ctx.project, ctx.fs, ctx.platform)
        names = ", ".join(map(quoted, scripts))
        changes = (f" It runs {names} from inside the project, which a pull can change without "
                   f"asking again." if scripts else "")
        result = Result.of(Code.TRUST_ASKED, f"io.trust would let io-guard start these commands from "
                           f"{ctx.project.as_posix()}/.claude/io-guard.json: "
                           f"{'; '.join(waiting.listed(ctx.held))}.{changes}", event.tool_name,
                           ctx.platform.os)
        return Decision(self.meta.id, Verdict.ASK, results=(result,))

    def config(self, event: Event, ctx: Context) -> Decision:
        spec = config_edit.needs_yes(event.tool_input, ctx.keys)
        if spec is None:
            return Decision.observe(self.meta.id)
        ctx.session.keep_ask(event.tool_use_id, config_edit.config_write(event.tool_input), ctx.clock.now())
        value = json.dumps(event.tool_input["value"], ensure_ascii=True)
        result = Result.of(Code.CONFIG_ASKED, f"io.config would set {event.tool_input['key']} to {value} in "
                           f"the user's own io-guard config.json, for every project. {spec.doc}",
                           event.tool_name, ctx.platform.os)
        return Decision(self.meta.id, Verdict.ASK, results=(result,))
