"""Run the verify command on a file after each Edit or Write, and hand its output to the agent.

The command comes from the verify key, per file extension and per project root (lib.commands): the user's own,
or the project's once the user approved it through io.trust. A project's command that waits for approval does
not run, and the agent hears so once per session as PROJECT_COMMANDS_UNTRUSTED. The command runs from an
argument list with no shell, in the session's folder, under a timeout, after verify.write has put back
anything the write lost. A command that passes and prints nothing adds nothing. Otherwise its exit code and
the head of its output reach the agent as VERIFY_OUTPUT, and so does a timeout or a program that cannot start,
so the telemetry counts each one.
"""
from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import commands, proc, runs, text, waiting
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.results import Code, Layer, Result, Severity


class VerifyCommand(Check):
    meta = CheckMeta(
        id="verify.command", layer=Layer.BYTES, events=frozenset({HookEvent.POST_TOOL_USE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=EVERY_PLATFORM,
        severity=Severity.WARNING, cost=Cost.EXPENSIVE, reads=frozenset({"file_path"}), writes=frozenset(),
        after=frozenset({"verify.write"}),
        config={"timeout_ms": ConfigKey(int, 10_000, "Milliseconds a verify command may run before io-guard "
                                        "stops it."),
                "output_chars": ConfigKey(int, 2_000, "The most characters of a verify command's output the "
                                          "agent sees.")},
        codes=frozenset({Code.VERIFY_OUTPUT, Code.PROJECT_COMMANDS_UNTRUSTED}),
        description="Runs the verify command named for the file's extension after each Edit or Write.")

    def said(self, *results: Result | None) -> Decision:
        """The results that exist, allowed, or an observation when there is none."""
        kept = tuple(result for result in results if result is not None)
        return Decision(self.meta.id, Verdict.ALLOW, results=kept) if kept else Decision.observe(self.meta.id)

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.file_path is None:
            return Decision.observe(self.meta.id)
        notice = waiting.untrusted(ctx.held, "verify", event.file_path, event.tool_name, ctx.platform,
                                   ctx.session.first_time)
        named = commands.command_for(ctx.config.get("verify"), event.file_path, ctx.platform)
        if named is None:
            return self.said(notice)
        command = commands.filled(named, event.file_path)
        timeout_ms = self.options["timeout_ms"]
        folders = runs.tool_folders(ctx.probe, ctx.platform, ctx.fs.is_dir)
        program, env = runs.start(command, ctx.env, folders) or (command, dict(ctx.env))
        done = proc.run(program, event.cwd, env, timeout_ms / 1000)
        shown = " ".join(command)
        output = text.head((done.stdout + done.stderr).decode("utf-8", "replace").strip(),
                           self.options["output_chars"])
        if done.start_error:
            lines = (f"io-guard could not start the verify command {shown}: {done.start_error}",)
        elif done.timed_out:
            lines = (f"io-guard stopped the verify command {shown} after {timeout_ms:,} ms, before it "
                     f"finished.",)
        elif done.ok and not output:
            return self.said(notice)
        else:
            lines = (f"io-guard ran {shown} after this {event.tool_name}, and it exited {done.exit_code}:",
                     output)
        message = "\n".join(line for line in lines if line)
        result = Result.of(Code.VERIFY_OUTPUT, message, event.tool_name, ctx.platform.os,
                           file=event.file_path, evidence={"command": shown, "exit_code": done.exit_code})
        return self.said(result, notice)
