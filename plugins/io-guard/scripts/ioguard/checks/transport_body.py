"""Move a Bash command's body into a file when the Bash tool would cut it or halve its backslashes.

On Windows the Bash tool cuts a command near 7,800 bytes and halves every pair of backslashes on the way to
bash (#92543). A quoted heredoc's body moves to a file and the command reads it through a stdin redirect, and
a python -c body moves and runs from its file. Both keep the command's meaning, and everything else in it
stays as written. A body moves only when the command is over the budget or the body holds a pair the halving
would change, so a short command runs untouched, and a moved body arrives byte-exact (D25). A command still
over the budget is refused with TRANSPORT_BUDGET, and a pair left outside a moved body gets a
BACKSLASH_TRANSPORT warning. The user's rewrite mode decides how a move is answered (D12), and the body file
is written in every mode, so a refusal's fix points at a file that exists.
"""
import hashlib
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import shell
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Fix, Layer, Result, Severity


def budget_for(ctx: Context) -> int | None:
    """The smallest of the budget key, the Bash tool's cut and the budget learned this session. None where the
    probe found no cut and the session learned none, and then no budget applies."""
    if ctx.probe.transport_budget is None and ctx.session.budget_override is None:
        return None
    limits = (ctx.config.get("transport.budget_bytes"), ctx.probe.transport_budget,
              ctx.session.budget_override)
    return min(limit for limit in limits if limit is not None)


def body_folder(event: Event, ctx: Context) -> Path | None:
    """The session scratchpad's io-guard folder, or bodies in io-guard's own, or None with neither."""
    if event.scratchpad is not None:
        return event.scratchpad / "io-guard"
    return None if ctx.data_dir is None else ctx.data_dir / "bodies"


def file_for(folder: Path, body: str, suffix: str) -> tuple[Path, bytes]:
    data = body.encode("utf-8")
    return folder / f"body-{hashlib.sha256(data).hexdigest()[:16]}{suffix}", data


def size(data: bytes) -> str:
    return f"{len(data) / 1024:.1f} KB"


class TransportBody(Check):
    meta = CheckMeta(
        id="transport.body", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH}), platforms=frozenset({"win32", "darwin"}), severity=Severity.FIXED,
        cost=Cost.MEDIUM, reads=frozenset({"command"}), writes=frozenset({"command"}),
        after=frozenset({"shell.writes"}),
        config={},
        codes=frozenset({Code.BODY_MOVED_TO_FILE, Code.TRANSPORT_BUDGET, Code.BACKSLASH_TRANSPORT}),
        description="Moves a Bash command's heredoc or python -c body into a file when the Bash tool would "
                    "cut the command or halve its backslashes.")

    def run(self, event: Event, ctx: Context) -> Decision:
        command, budget, halving = event.command or "", budget_for(ctx), ctx.probe.halving is True
        if budget is None and not halving:
            return Decision.observe(self.meta.id)
        scan = shell.scan(command)
        over = budget is not None and shell.budget_length(command) > budget

        def halved(span: tuple[int, int]) -> bool:
            return halving and any(span[0] <= offset < span[1] for offset in scan.hazards)

        heredocs = [heredoc for heredoc in scan.heredocs if heredoc.quoted and heredoc.terminated
                    and (over or halved(heredoc.span))]
        bodies = [body for body in scan.bodies if not body.expands and (over or halved(body.argument))]
        folder = body_folder(event, ctx)
        if folder is None or not (heredocs or bodies):
            return self.as_it_runs(event, ctx, command, budget)
        files = {heredoc: file_for(folder, heredoc.body, ".txt") for heredoc in heredocs}
        files |= {body: file_for(folder, body.body, ".py") for body in bodies}
        ctx.fs.make_folders(folder)
        for path, data in files.values():
            ctx.fs.write_atomic(path, data)
        paths = {part: path.as_posix() for part, (path, _) in files.items()}
        rewritten = shell.moved(command, {heredoc: paths[heredoc] for heredoc in heredocs},
                                {body: paths[body] for body in bodies})
        running = self.as_it_runs(event, ctx, rewritten, budget)
        if running.verdict is Verdict.DENY:
            return running
        moves = ", ".join(f"a {size(data)} {'heredoc' if part in heredocs else 'python -c'} body to "
                          f"{path.as_posix()}" for part, (path, data) in files.items())
        note = (f"io-guard moved {moves}, and the command reads it from there. The body arrives exactly as "
                f"written, with no backslash halved.")
        rewrite = Rewrite(self.meta.id, frozenset({"command"}),
                          lambda given: {**given, "command": rewritten}, note, Code.BODY_MOVED_TO_FILE)
        return Decision(self.meta.id, Verdict.ALLOW, results=running.results, rewrite=rewrite)

    def as_it_runs(self, event: Event, ctx: Context, command: str, budget: int | None) -> Decision:
        """The command as it would run: refused over the budget, and warned about a pair of backslashes the
        Bash tool halves. A warning only, because agents double their backslashes to survive the halving,
        and a refusal would stop 1% of the calls that ran (D25). OBSERVE when neither holds."""
        length = shell.budget_length(command)
        if budget is not None and length > budget:
            result = Result.of(Code.TRANSPORT_BUDGET,
                               f"This command is {length:,} bytes as the Bash tool counts them, over the "
                               f"{budget:,}-byte budget, and the Bash tool cuts commands near 7,800 bytes.",
                               event.tool_name, ctx.platform.os, evidence={"bytes": length, "budget": budget},
                               fix=Fix("Write", {}, "Write the script to a file with the Write tool, then "
                                                    "run the file."))
            return Decision(self.meta.id, Verdict.DENY, results=(result,))
        hazards = shell.scan(command).hazards if ctx.probe.halving is True else ()
        if hazards:
            at = hazards[0]
            shown = command[max(0, at - 20):at + 22].replace("\n", " ")
            result = Result.of(Code.BACKSLASH_TRANSPORT,
                               f"The Bash tool on Windows halves a pair of backslashes that no double quote "
                               f"follows, so bash reads one backslash where this command has two, as in: "
                               f"{shown}", event.tool_name, ctx.platform.os,
                               evidence={"offsets": list(hazards[:10])},
                               fix=Fix("Write", {}, "If the command needs both, put that text in a file with "
                                                    "the Write tool and have the command read it."))
            return Decision(self.meta.id, Verdict.ALLOW, results=(result,))
        return Decision.observe(self.meta.id)
