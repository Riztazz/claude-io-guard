"""io.trust: let io-guard start the commands a project's .claude/io-guard.json names, once the user approves.

A project file's verify and format commands wait until the user approves that exact set (lib.trust). The
PreToolUse hook on this call puts them to the user in Claude Code's permission prompt (checks.trust_ask), and
this tool writes the approval only for commands that hook asked about, so a hook that failed open approves
nothing and the model cannot approve for the user.
"""
from dataclasses import dataclass

from ioguard.lib import trust, waiting
from ioguard.lib.folders import project_root
from ioguard.lib.results import Code
from ioguard.mcp.in_place import refused
from ioguard.mcp.toolspec import ToolCall, ToolSpec, doc

NAME = "io.trust"


@dataclass(frozen=True)
class TrustInput:
    pass


@dataclass(frozen=True)
class TrustOutput:
    project: str = doc("The project whose commands the call is about.")
    commands: list[str] = doc("Each command the project's config names, as key, extension and words.")
    approved: bool = doc("True when the user approved them and they run from the next tool call.")

    def render(self) -> str:
        if not self.commands:
            return f"{self.project}/.claude/io-guard.json names no command waiting for approval."
        return (f"The user approved these commands for {self.project}, and io-guard starts them from the "
                f"next tool call: {'; '.join(self.commands)}.")


def approve(given: TrustInput, call: ToolCall) -> TrustOutput:
    ctx, root = call.context, project_root(call.cwd)
    if not ctx.held or ctx.data_dir is None:
        return TrustOutput(root.as_posix(), [], False)
    if not ctx.session.take_ask(call.tool_use_id, trust.fingerprint(ctx.held), ctx.clock.now()):
        raise refused(Code.TRUST_ASKED, f"{NAME} approved nothing, because no permission prompt on this call "
                      f"put the project's commands to the user.", NAME, root / ".claude" / "io-guard.json",
                      ctx)
    trust.approve(ctx.data_dir, root, ctx.held, ctx.clock.now())
    return TrustOutput(root.as_posix(), waiting.listed(ctx.held), True)


SPECS = (ToolSpec(NAME, "Ask the user to approve a project's commands",
                  "Puts the verify and format commands a project's .claude/io-guard.json names to the user, "
                  "and lets io-guard start them once the user says yes. Use it when io-guard says "
                  "PROJECT_COMMANDS_UNTRUSTED.",
                  TrustInput, TrustOutput, read_only=False, destructive=False, idempotent=True,
                  handler=approve),)
