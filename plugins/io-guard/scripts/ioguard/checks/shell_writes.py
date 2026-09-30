"""Refuse a shell command that writes a file git tracks, and name the tool that writes it safely.

A write through the shell skips io-guard's byte checks and Claude Code's checkpoints (SHW-1). lib.writes finds
each write a command makes. The check refuses a write only when git tracks its target, and the refusal of an
in-place edit, such as sed -i or a script body, names io.edit, which makes several changes in one call. A
write to the scratchpad, to a device, or outside any repository passes. A target built from a variable, or
named after a cd the check cannot follow, passes too. Git's answer for a path holds for the session until a
command names git, which can add or remove a file. A script file that writes to a path it does not spell
out, given a tracked file, gets a warning that names io.edit, or io.format when it runs a formatter. A script
file the shell creates inside a repository gets a warning that points at the scratchpad (GIT-1).
"""
import re
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.git import GitError
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.results import Code, Fix, Layer, Result, Severity, callable_name
from ioguard.lib.session import tracked
from ioguard.lib.writes import (Host, Script, Write, bash_writes, powershell_writes, resolve, script_files,
                                targets)

VARIABLE_WRITE = re.compile(r"open\(\s*(?!r?['\"])[^,()]+,\s*(?:mode\s*=\s*)?r?['\"][wax]"
                            r"|\.write_(?:text|bytes)\("
                            r"|(?:writeFileSync|appendFileSync|writeFile)\(\s*(?!['\"])")
FORMATTERS = re.compile(r"clang-format|black|prettier|rustfmt|gofmt|autopep8|yapf|isort", re.I)
SCRIPT_SUFFIXES = {".py", ".sh", ".ps1", ".psm1", ".js", ".bat", ".cmd", ".rb", ".pl"}
IN_PLACE = {"a script body", "a script file"}   # with every ... -i, writes that change a file in places
RUNS_GIT = re.compile(r"(?<![\w.-])git(?:\.exe)?(?=\s|$)", re.I)


def inside(path: Path, folder: Path | None) -> bool:
    if folder is None:
        return False
    try:
        return path.is_relative_to(folder)
    except ValueError:
        return False


class ShellWrites(Check):
    meta = CheckMeta(
        id="shell.writes", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL}), platforms=EVERY_PLATFORM,
        severity=Severity.REFUSED, cost=Cost.EXPENSIVE, reads=frozenset({"command"}), writes=frozenset(),
        after=frozenset(), config={}, codes=frozenset({Code.SHELL_WRITE}),
        description="Refuses a shell command that writes a file git tracks, and names the tool that writes "
                    "it safely.")

    def run(self, event: Event, ctx: Context) -> Decision:
        command, host = event.command or "", Host.of(ctx)
        if RUNS_GIT.search(command):
            with ctx.session.lock:
                ctx.session.tracked.clear()
        bash = event.tool is not Tool.POWERSHELL
        scripts = script_files(command, event.cwd, host) if bash else []
        found = (bash_writes(command, event.cwd, host, scripts=scripts) if bash
                 else powershell_writes(command, event.cwd, host))
        refusals, warnings = [], []
        for write in found:
            for path in targets(write, host):
                if inside(path, event.scratchpad):
                    continue
                state = tracked(path, ctx.git, ctx.session)
                if state:
                    refusals.append(self.refusal(write, path, event, ctx))
                elif (state is False and path.suffix.lower() in SCRIPT_SUFFIXES
                      and self.in_repository(path, ctx)):
                    warnings.append(self.warning(path, event, ctx))
        warnings += [warning for script in scripts if (warning := self.given(script, event, ctx)) is not None]
        if refusals:
            return Decision(self.meta.id, Verdict.DENY, results=tuple(refusals[:1]) + tuple(warnings))
        if warnings:
            return Decision(self.meta.id, Verdict.ALLOW, results=tuple(warnings[:1]))
        return Decision.observe(self.meta.id)

    @staticmethod
    def in_repository(path: Path, ctx: Context) -> bool:
        try:
            return ctx.git.root(path) is not None
        except GitError:
            return False

    @staticmethod
    def refusal(write: Write, path: Path, event: Event, ctx: Context) -> Result:
        if write.how in IN_PLACE or " -i" in write.how:
            batch = callable_name("io.edit")
            fix = Fix(batch, {"path": path.as_posix()}, f"Use {batch} to make several changes in one call, "
                                                        "the Edit tool for one, or the Write tool to replace "
                                                        "it whole.")
        else:
            fix = Fix("Edit", {"file_path": path.as_posix()},
                      "Use the Edit tool to change it, or the Write tool to replace it whole.")
        return Result.of(Code.SHELL_WRITE,
                         f"This command writes {path.as_posix()}, which git tracks, through {write.how}, "
                         "so the write skips io-guard's byte checks and Claude Code's checkpoints.",
                         event.tool_name, ctx.platform.os, file=path,
                         evidence={"target": write.target, "how": write.how}, fix=fix)

    @staticmethod
    def given(script: Script, event: Event, ctx: Context) -> Result | None:
        """A warning when a script that writes to a path it does not spell out is given a tracked file."""
        if not VARIABLE_WRITE.search(script.body):
            return None
        for word in script.arguments:
            path = None if word.startswith("-") else resolve(word, script.cwd, Host.of(ctx))
            if path is None or inside(path, event.scratchpad) or not tracked(path, ctx.git, ctx.session):
                continue
            tool = callable_name("io.format" if FORMATTERS.search(script.body) else "io.edit")
            message = (f"This command gives {path.as_posix()}, which git tracks, to {script.path.name}, a "
                       f"script that writes files it is given, so the write would skip io-guard's byte "
                       f"checks and Claude Code's checkpoints.")
            return Result.of(Code.SHELL_WRITE, message, event.tool_name, ctx.platform.os,
                             severity=Severity.WARNING, file=path,
                             evidence={"script": script.path.as_posix(), "target": word},
                             fix=Fix(tool, {"path": path.as_posix()}, f"Use {tool} to change it instead."))
        return None

    @staticmethod
    def warning(path: Path, event: Event, ctx: Context) -> Result:
        folder = "the session scratchpad" if event.scratchpad is None else event.scratchpad.as_posix()
        return Result.of(Code.SHELL_WRITE,
                         f"This command creates the script {path.as_posix()} inside the repository, "
                         "where git sees it as a new file.", event.tool_name, ctx.platform.os,
                         severity=Severity.WARNING, file=path,
                         fix=Fix("Write", {}, f"Put a scratch script in {folder} instead."))
