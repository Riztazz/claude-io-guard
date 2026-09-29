"""Refuse a git commit whose message holds what the user's commit policy forbids, before it runs.

Rules in CLAUDE.md are context, not configuration, and a model that writes a co-author line out of habit
writes it again the next time. The policy is two keys: commit_policy.forbid, texts no message may hold,
matched without case, such as Co-Authored-By, and commit_policy.ascii_only. Both are empty by default, so
the check refuses nothing until a user or a project names them. The message comes from each -m, from a -F
file, from the heredoc a -F - reads, and from a PowerShell here-string, which arrives as the -m word. An
io.run call's argument list is read the same way, and so is the string a shell in it is given and a Bash or
PowerShell body, so a commit through io.run meets the same policy.
"""
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import commit_message, pwsh, rules, runs, shell
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Fix, Layer, Result, Severity, callable_name

RUN = callable_name("io.run")
FILE_BYTES = 64 * 1024


def messages(event: Event, ctx: Context) -> list[str]:
    """The message text of each git commit the call runs."""
    if event.tool_name == RUN:
        return run_messages(event.tool_input, event.cwd, ctx)
    if event.tool is Tool.POWERSHELL:
        return powershell_messages(event.command or "", event.cwd, ctx)
    return bash_messages(event.command or "", event.cwd, ctx)


def run_messages(given: dict, cwd: Path, ctx: Context) -> list[str]:
    """The messages an io.run call commits: from its argv, from the string a shell in it is given, or from a
    Bash or PowerShell body. A body in another language is left unread."""
    match given.get("lang") if given.get("code") else None:
        case "bash":
            return bash_messages(str(given["code"]), cwd, ctx)
        case "powershell":
            return powershell_messages(str(given["code"]), cwd, ctx)
    argv = runs.argv_of(given, ctx.probe, ctx.platform) or ()
    found = commit_message.sources(argv)
    if found is not None:
        return [text(found, (), cwd, ctx)]
    inside = rules.wrapped(rules.unwrapped(argv))
    if inside is None or inside.text is None:
        return []
    return (bash_messages if inside.dialect == "bash" else powershell_messages)(inside.text, cwd, ctx)


def powershell_messages(command: str, cwd: Path, ctx: Context) -> list[str]:
    return [text(found, (), cwd, ctx) for simple in pwsh.commands(command)
            if (found := commit_message.sources(simple.words)) is not None]


def bash_messages(command: str, cwd: Path, ctx: Context) -> list[str]:
    heredocs = shell.scan(command).heredocs
    out = []
    for simple in shell.commands(command):
        found = commit_message.sources(simple.words)
        if found is not None:
            start, end = simple.span
            stdin = tuple(heredoc.body for heredoc in heredocs if start <= heredoc.operator[0] < end)
            out.append(text(found, stdin, cwd, ctx))
    return out


def text(found: commit_message.Sources, stdin: tuple[str, ...], cwd: Path, ctx: Context) -> str:
    """Every part of one message: its -m texts, then each -F file, or the heredoc for -F -."""
    parts = list(found.texts)
    for name in found.files:
        if name == "-":
            parts += stdin
            continue
        try:
            parts.append(ctx.fs.read_bytes(cwd / name, FILE_BYTES).decode("utf-8", "replace"))
        except OSError:
            continue
    return "\n\n".join(parts)


class CommitPolicy(Check):
    meta = CheckMeta(
        id="commit.policy", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL, Tool.OTHER}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.REFUSED, cost=Cost.CHEAP, reads=frozenset({"command", "argv", "lang", "code"}),
        writes=frozenset(), after=frozenset(), config={}, codes=frozenset({Code.COMMIT_POLICY}),
        description="Refuses a git commit whose message holds text the commit policy forbids.")

    def run(self, event: Event, ctx: Context) -> Decision:
        forbid = ctx.config.get("commit_policy.forbid")
        ascii_only = ctx.config.get("commit_policy.ascii_only")
        if (not forbid and not ascii_only) or (event.tool is Tool.OTHER and event.tool_name != RUN):
            return Decision.observe(self.meta.id)
        found = [problem for message in messages(event, ctx)
                 for problem in commit_message.problems(message, forbid, ascii_only)]
        if not found:
            return Decision.observe(self.meta.id)
        named = ", ".join(f"{problem.what} on line {problem.line}" for problem in found)
        wide = any(problem.what.startswith("U+") for problem in found)
        fix = Fix(event.tool_name, {}, ("Write the message in ASCII" if wide else "Take that text out of the "
                                        "message") + ", then commit again with the same command.")
        result = Result.of(Code.COMMIT_POLICY, f"The commit message holds {named}, which the commit policy "
                           f"forbids, so the commit did not run.", event.tool_name, ctx.platform.os, fix=fix,
                           evidence={"found": [problem.what for problem in found]})
        return Decision(self.meta.id, Verdict.DENY, results=(result,))
