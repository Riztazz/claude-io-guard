"""Put a command io-guard would start to the user, at the PreToolUse hook on the call that would let it run,
and say once per session when a project's command waits for approval.

A project's .claude/io-guard.json may name verify and format commands, which io-guard starts (lib.trust). On
io.trust the check answers ask with TRUST_ASKED, listing each command, so Claude Code shows its own permission
prompt, the one control the model cannot answer for the user. The prompt says when a command runs a file from
inside the project, since a pull can change that file and leave the command as it was. On io.config it answers
ask with CONFIG_ASKED for a write of a key marked runs into the user's own file, which reaches every project.
Each ask is recorded under the call's tool use id, and the tool acts only on the ask its own hook recorded, so
a hook that failed open approves nothing.
"""
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import commands, trust
from ioguard.lib.config import ConfigKey, all_keys
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Layer, Result, Severity, callable_name
from ioguard.lib.text import quoted

TRUST = callable_name("io.trust")
CONFIG = callable_name("io.config")


def listed(held: Mapping[str, Any]) -> list[str]:
    """Each held command as one line: its key, where it applies and its words, each word the project's file
    names quoted as JSON, such as verify ".py": "python" "x"."""
    lines = []
    for key, value in sorted(held.items()):
        for name, entry in sorted(value.items()):
            pairs = entry.items() if not name.startswith(".") else [(name, entry)]
            where = "" if name.startswith(".") else f" in {quoted(name)}"
            lines += [f"{key} {quoted(extension)}{where}: {' '.join(map(quoted, argv))}"
                      for extension, argv in sorted(pairs)]
    return lines


def inside(held: Mapping[str, Any], project: Path) -> list[str]:
    """The words of the held commands that name a file inside project, which a pull can change."""
    found = []
    for value in held.values():
        for name, entry in value.items():
            for argv in ([entry] if name.startswith(".") else entry.values()):
                for word in argv:
                    path = Path(word) if Path(word).is_absolute() else project / word
                    if path.is_file() and path.resolve().is_relative_to(project.resolve()):
                        found.append(word)
    return sorted(set(found))


def untrusted(ctx: Context, key: str, path: Path, tool: str, platform: Platform) -> Result | None:
    """PROJECT_COMMANDS_UNTRUSTED, once per session, when the project names a key command for path that the
    user has not approved, else None."""
    if commands.command_for(ctx.held.get(key, {}), path, platform) is None:
        return None
    if not ctx.session.first_time(f"untrusted:{trust.fingerprint(ctx.held)}"):
        return None
    waiting = "; ".join(listed(ctx.held))
    return Result.of(Code.PROJECT_COMMANDS_UNTRUSTED, f"The project's .claude/io-guard.json names commands "
                     f"the user has not approved, so io-guard ran none of them: {waiting}.", tool,
                     platform.os, file=path)


def config_keys() -> dict[str, ConfigKey]:
    """Every setting io-guard has, by its dotted key."""
    from ioguard.checks.registry import default_registry     # the registry imports this module
    return all_keys(default_registry().keys())


def needs_yes(tool_input: Mapping[str, Any]) -> ConfigKey | None:
    """The setting an io.config call would write into the user's own file when it names a program io-guard
    starts or a variable one reads, else None. A read, a removal and a project file's write ask nothing: a
    project's value of such a key waits for io.trust."""
    key, scope = tool_input.get("key"), tool_input.get("scope", "user")
    writes = tool_input.get("value") is not None and not tool_input.get("remove")
    if not writes or scope != "user" or not isinstance(key, str):
        return None
    spec = config_keys().get(key)
    return spec if spec is not None and spec.runs else None


def config_write(tool_input: Mapping[str, Any]) -> str:
    """The one io.config write an ask is about: its key, its scope and its value, as canonical JSON."""
    return json.dumps({"key": tool_input.get("key"), "scope": tool_input.get("scope", "user"),
                       "value": tool_input.get("value")}, sort_keys=True, ensure_ascii=True)


class TrustAsk(Check):
    meta = CheckMeta(
        id="trust.ask", layer=Layer.INTERNAL, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.OTHER}), platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING,
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
        scripts = inside(ctx.held, ctx.project)
        names = ", ".join(map(quoted, scripts))
        changes = (f" It runs {names} from inside the project, which a pull can change without "
                   f"asking again." if scripts else "")
        result = Result.of(Code.TRUST_ASKED, f"io.trust would let io-guard start these commands from "
                           f"{ctx.project.as_posix()}/.claude/io-guard.json: {'; '.join(listed(ctx.held))}."
                           f"{changes}", event.tool_name, ctx.platform.os)
        return Decision(self.meta.id, Verdict.ASK, results=(result,))

    def config(self, event: Event, ctx: Context) -> Decision:
        spec = needs_yes(event.tool_input)
        if spec is None:
            return Decision.observe(self.meta.id)
        ctx.session.keep_ask(event.tool_use_id, config_write(event.tool_input), ctx.clock.now())
        value = json.dumps(event.tool_input["value"], ensure_ascii=True)
        result = Result.of(Code.CONFIG_ASKED, f"io.config would set {event.tool_input['key']} to {value} in "
                           f"the user's own io-guard config.json, for every project. {spec.doc}",
                           event.tool_name, ctx.platform.os)
        return Decision(self.meta.id, Verdict.ASK, results=(result,))
