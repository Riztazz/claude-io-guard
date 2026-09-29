"""Put a project's commands to the user when io.trust would approve them, at the PreToolUse hook on its own
call, and say once per session when a project's command waits for approval.

A project's .claude/io-guard.json may name verify and format commands, which io-guard starts (lib.trust). The
check answers ask with TRUST_ASKED, listing each command, so Claude Code shows its own permission prompt, the
one control the model cannot answer for the user. It records the fingerprint it put to the user, and io.trust
writes an approval only for a fingerprint this hook asked about, so a hook that failed open approves nothing.
The prompt says when a command runs a file from inside the project, since a pull can change that file and
leave the command as it was.
"""
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import commands, trust
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Layer, Result, Severity, callable_name

TRUST = callable_name("io.trust")


def listed(held: Mapping[str, Any]) -> list[str]:
    """Each held command as one line: its key, where it applies and its words, such as "verify .py: python
    x"."""
    lines = []
    for key, value in sorted(held.items()):
        for name, entry in sorted(value.items()):
            pairs = entry.items() if not name.startswith(".") else [(name, entry)]
            where = "" if name.startswith(".") else f" in {name}"
            lines += [f"{key} {extension}{where}: {' '.join(argv)}" for extension, argv in sorted(pairs)]
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


class TrustAsk(Check):
    meta = CheckMeta(
        id="trust.ask", layer=Layer.INTERNAL, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.OTHER}), platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING,
        cost=Cost.CHEAP, reads=frozenset(), writes=frozenset(), after=frozenset(), config={},
        codes=frozenset({Code.TRUST_ASKED}),
        description="Asks the user before io.trust approves the commands a project's config names.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.tool_name != TRUST or not ctx.held or ctx.project is None:
            return Decision.observe(self.meta.id)
        with ctx.session.lock:
            ctx.session.asked_trust.add(trust.fingerprint(ctx.held))
        scripts = inside(ctx.held, ctx.project)
        changes = (f" It runs {', '.join(scripts)} from inside the project, which a pull can change without "
                   f"asking again." if scripts else "")
        result = Result.of(Code.TRUST_ASKED, f"io.trust would let io-guard start these commands from "
                           f"{ctx.project.as_posix()}/.claude/io-guard.json: {'; '.join(listed(ctx.held))}."
                           f"{changes}", event.tool_name, ctx.platform.os)
        return Decision(self.meta.id, Verdict.ASK, results=(result,))
