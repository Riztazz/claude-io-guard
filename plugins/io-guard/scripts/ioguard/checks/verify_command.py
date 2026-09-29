"""Run the user's verify command on a file after each Edit or Write, and hand its output to the agent.

The command comes from the verify key in the user's own config.json, per file extension and per project
root (lib.commands). A project file cannot name one (D24). It runs from an argument list with no shell, in the
session's folder, under a timeout, after verify.write has put back anything the write lost. A command that
passes and prints nothing adds nothing. Otherwise its exit code and the head of its output reach the agent as
VERIFY_OUTPUT, and so does a timeout or a program that cannot start, so the telemetry counts each one.
"""
from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import commands, proc, text
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Layer, Result, Severity


class VerifyCommand(Check):
    meta = CheckMeta(
        id="verify.command", layer=Layer.BYTES, events=frozenset({HookEvent.POST_TOOL_USE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.WARNING, cost=Cost.EXPENSIVE, reads=frozenset({"file_path"}), writes=frozenset(),
        after=frozenset({"verify.write"}),
        config={"timeout_ms": ConfigKey(int, 10_000, "Milliseconds a verify command may run before io-guard "
                                        "stops it.", project_narrows=True),
                "output_chars": ConfigKey(int, 2_000, "The most characters of a verify command's output the "
                                          "agent sees.")},
        codes=frozenset({Code.VERIFY_OUTPUT}),
        description="Runs the verify command the user names for the file's extension after each Edit or "
                    "Write.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.file_path is None:
            return Decision.observe(self.meta.id)
        named = commands.command_for(ctx.config.get("verify"), event.file_path, ctx.platform)
        if named is None:
            return Decision.observe(self.meta.id)
        command = commands.filled(named, event.file_path)
        timeout_ms = self.options["timeout_ms"]
        done = proc.run(command, event.cwd, ctx.env, timeout_ms / 1000)
        shown = " ".join(command)
        output = text.head((done.stdout + done.stderr).decode("utf-8", "replace").strip(),
                           self.options["output_chars"])
        if done.start_error:
            lines = (f"io-guard could not start the verify command {shown}: {done.start_error}",)
        elif done.timed_out:
            lines = (f"io-guard stopped the verify command {shown} after {timeout_ms:,} ms, before it "
                     f"finished.",)
        elif done.ok and not output:
            return Decision.observe(self.meta.id)
        else:
            lines = (f"io-guard ran {shown} after this {event.tool_name}, and it exited {done.exit_code}:",
                     output)
        message = "\n".join(line for line in lines if line)
        result = Result.of(Code.VERIFY_OUTPUT, message, event.tool_name, ctx.platform.os,
                           file=event.file_path, evidence={"command": shown, "exit_code": done.exit_code})
        return Decision(self.meta.id, Verdict.ALLOW, results=(result,))
