"""Refuse a git commit whose message holds what the user's commit policy forbids, before it runs.

Rules in CLAUDE.md are context, not configuration, and a model that writes a co-author line out of habit
writes it again the next time. The policy is two keys: commit_policy.forbid, texts no message may hold,
matched without case, such as Co-Authored-By, and commit_policy.ascii_only. Both are empty by default, so
the check refuses nothing until a user or a project names them. The message comes from each -m, from a -F
file, from the heredoc a -F - reads, and from a PowerShell here-string, which arrives as the -m word. A -F
file resolves after the command's cd. One the command writes from a heredoc, as cat > m.txt <<'EOF' does,
is read from that heredoc. One it writes another way, or one not there yet, cannot be read before the commit
runs, so the commit is refused with the step of writing the file first. An
io.run call's argument list is read the same way, and so is the string a shell in it is given and a Bash or
PowerShell body, so a commit through io.run meets the same policy.
"""
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import commit_message, pwsh, rules, runs, shell
from ioguard.lib.context import Context, read_or_none
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.results import Code, Fix, Layer, Result, Severity, callable_name
from ioguard.lib.writes import Host, Write, bash_writes, located, powershell_writes, resolve, targets

RUN = callable_name("io.run")
FILE_BYTES = 64 * 1024


@dataclass(frozen=True)
class Message:
    text: str
    unread: tuple[str, ...]         # each -F file io-guard cannot read before the command runs


def messages(event: Event, ctx: Context) -> list[Message]:
    """The message of each git commit the call runs."""
    if event.tool_name == RUN:
        return run_messages(event, ctx)
    if event.tool is Tool.POWERSHELL:
        return powershell_messages(event.command or "", event, event.cwd, ctx)
    return bash_messages(event.command or "", event, event.cwd, ctx)


def run_messages(event: Event, ctx: Context) -> list[Message]:
    """The messages an io.run call commits: from its argv, from the string a shell in it is given, or from a
    Bash or PowerShell body. A body in another language is left unread."""
    given, cwd = event.tool_input, event.cwd
    match given.get("lang") if given.get("code") else None:
        case "bash":
            return bash_messages(str(given["code"]), event, cwd, ctx)
        case "powershell":
            return powershell_messages(str(given["code"]), event, cwd, ctx)
    argv = runs.argv_of(given, ctx.probe, ctx.platform, ctx.env) or ()
    found = commit_message.sources(argv)
    if found is not None:
        return [message(found, (), cwd, {}, ctx)]
    inside = rules.wrapped(rules.unwrapped(argv))
    if inside is None or inside.text is None:
        return []
    reader = bash_messages if inside.dialect is rules.Dialect.BASH else powershell_messages
    return reader(inside.text, event, cwd, ctx)


def powershell_messages(command: str, event: Event, cwd: Path, ctx: Context) -> list[Message]:
    found = [each for simple in pwsh.commands(command)
             if (each := commit_message.sources(simple.words)) is not None]
    if not reads_a_file(found):
        return [message(each, (), cwd, {}, ctx) for each in found]
    written = landed(powershell_writes(command, event.cwd, Host.of(ctx), cwd), ctx)
    return [message(each, (), cwd, written, ctx) for each in found]


def bash_messages(command: str, event: Event, cwd: Path, ctx: Context) -> list[Message]:
    scan = shell.scan(command)
    placed = located(command, scan, cwd, Host.of(ctx))
    commits = [(simple, where, each) for simple, where in placed
               if (each := commit_message.sources(simple.words)) is not None]
    written = {}
    if reads_a_file([each for _, _, each in commits]):
        writes = bash_writes(command, event.cwd, Host.of(ctx), cwd)
        written = landed(writes, ctx) | heredoc_files(scan, placed, ctx)
    out = []
    for simple, where, found in commits:
        stdin = tuple(heredoc.body for heredoc in within(scan, simple))
        out.append(message(found, stdin, where, written, ctx))
    return out


def landed(writes: list[Write], ctx: Context) -> dict[Path | str, str | None]:
    """Each file the command writes, with no text known for it yet."""
    return {path: None for write in writes for path in targets(write, Host.of(ctx))}


def reads_a_file(found: list[commit_message.Sources]) -> bool:
    return any(name != "-" for each in found for name in each.files)


def within(scan: shell.Scan, simple: shell.SimpleCommand) -> list[shell.Heredoc]:
    start, end = simple.span
    return [heredoc for heredoc in scan.heredocs if start <= heredoc.operator[0] < end]


def heredoc_files(scan: shell.Scan, placed: list[tuple[shell.SimpleCommand, Path | None]],
                  ctx: Context) -> dict[Path | str, str]:
    """The text each cat > file <<'EOF' writes, by the target as written and by its path, where bash passes
    the heredoc as it stands."""
    found: dict[Path | str, str] = {}
    for simple, where in placed:
        bodies = [heredoc.body for heredoc in within(scan, simple) if heredoc.terminated
                  and (heredoc.quoted or not re.search(r"[$`\\]", heredoc.body))]
        if simple.name != "cat" or len(simple.words) != 1 or len(simple.redirects) != 1 or len(bodies) != 1:
            continue
        redirect = simple.redirects[0]
        if redirect.append or redirect.fd not in (None, 1):
            continue
        found[redirect.target] = bodies[0]
        if (path := resolve(redirect.target, where, Host.of(ctx))) is not None:
            found[path] = bodies[0]
    return found


def message(found: commit_message.Sources, stdin: tuple[str, ...], cwd: Path | None,
            written: Mapping[Path | str, str | None], ctx: Context) -> Message:
    """Every part of one message: its -m texts, then each -F file, or the heredoc for -F -. A file the
    command writes from a heredoc is that heredoc. A file it writes another way, or one io-guard cannot read,
    is unread, since git reads it only once the command runs."""
    parts, unread = list(found.texts), []
    for name in found.files:
        if name == "-":
            parts += stdin
            continue
        path = resolve(name, cwd, Host.of(ctx))
        if written.get(name) is not None or (path is not None and written.get(path) is not None):
            parts.append(written.get(name) or written[path])
            continue
        data = None if path is None or path in written else read_or_none(ctx.fs, path, FILE_BYTES)
        if data is None:
            unread.append(name)
        else:
            parts.append(data.decode("utf-8", "replace"))
    return Message("\n\n".join(parts), tuple(unread))


class CommitPolicy(Check):
    meta = CheckMeta(
        id="commit.policy", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL, Tool.OTHER}), platforms=EVERY_PLATFORM,
        severity=Severity.REFUSED, cost=Cost.CHEAP, reads=frozenset({"command", "argv", "lang", "code"}),
        writes=frozenset(), after=frozenset(), config={}, codes=frozenset({Code.COMMIT_POLICY}),
        description="Refuses a git commit whose message holds text the commit policy forbids.")

    def run(self, event: Event, ctx: Context) -> Decision:
        forbid = ctx.config.get("commit_policy.forbid")
        ascii_only = ctx.config.get("commit_policy.ascii_only")
        if (not forbid and not ascii_only) or (event.tool is Tool.OTHER and event.tool_name != RUN):
            return Decision.observe(self.meta.id)
        given = messages(event, ctx)
        unread = [name for each in given for name in each.unread]
        if unread:
            return Decision(self.meta.id, Verdict.DENY, results=(self.unread(unread, event, ctx),))
        found = [problem for each in given
                 for problem in commit_message.problems(each.text, forbid, ascii_only)]
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

    @staticmethod
    def unread(names: list[str], event: Event, ctx: Context) -> Result:
        name = names[0]
        message = (f"io-guard cannot read the message file {name} before this command runs, since the "
                   f"command writes it or it is not there yet, so the commit did not run.")
        fix = Fix(event.tool_name, {}, f"Write {name} in one call, then commit with -F {name} in the next.")
        return Result.of(Code.COMMIT_POLICY, message, event.tool_name, ctx.platform.os, fix=fix,
                         evidence={"unread": names})
