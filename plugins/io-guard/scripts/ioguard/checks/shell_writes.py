"""Refuse a shell command that writes a file git tracks, and name the tool that writes it safely.

A write through the shell skips io-guard's byte checks and Claude Code's checkpoints (SHW-1). The check finds
each write a command makes: a > or >> redirect, sed -i and perl -i, tee, cp and mv, a heredoc or python -c
body that opens a file for writing, a body transport.body moved into a file, a script file an interpreter
runs, and PowerShell's Set-Content,
Add-Content, Out-File, Copy-Item, Move-Item, Tee-Object and [IO.File] calls. The check refuses a write only
when git tracks its target, and the refusal of an in-place edit, such as sed -i or a script body, names
io.edit, which makes several changes in one call. A write to the scratchpad, to a device, or outside any
repository passes. A target built from a variable, or named after a cd the check cannot follow, passes too.
A script file that writes to a path it does not spell out, given a tracked file, gets a warning that names
io.edit, or io.format when it runs a formatter. A script file the shell creates inside a repository gets a
warning that points at the scratchpad (GIT-1). A
stream redirect such as 2>&1 writes no file (SHW-8). A command's words inside a script body's string are
data, not a write (GRD-1).
"""
import re
from dataclasses import dataclass
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import paths, pwsh, shell
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.git import GitError
from ioguard.lib.results import Code, Fix, Layer, Result, Severity, callable_name

DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "nul", "$null", "con"}
SCRIPT_BYTES = 1024 * 1024       # a script file past this is not read
VARIABLE_WRITE = re.compile(r"open\(\s*(?!r?['\"])[^,()]+,\s*(?:mode\s*=\s*)?r?['\"][wax]"
                            r"|\.write_(?:text|bytes)\("
                            r"|(?:writeFileSync|appendFileSync|writeFile)\(\s*(?!['\"])")
FORMATTERS = re.compile(r"clang-format|black|prettier|rustfmt|gofmt|autopep8|yapf|isort", re.I)
SCRIPT_SUFFIXES = {".py", ".sh", ".ps1", ".psm1", ".js", ".bat", ".cmd", ".rb", ".pl"}
SCRIPT_WRITE = re.compile(
    r"open\(\s*r?(['\"])(?P<open>[^'\"]+)\1\s*,\s*(?:mode\s*=\s*)?r?['\"][wax]"
    r"|Path\(\s*r?(['\"])(?P<path>[^'\"]+)\3\s*\)\.write_(?:text|bytes)\("
    r"|(?:writeFileSync|appendFileSync|writeFile)\(\s*(['\"])(?P<node>[^'\"]+)\5")
PS_WRITERS = {"set-content": ("-path", "-literalpath"), "sc": ("-path", "-literalpath"),
              "add-content": ("-path", "-literalpath"), "ac": ("-path", "-literalpath"),
              "out-file": ("-filepath", "-literalpath", "-path"), "tee-object": ("-filepath", "-path"),
              "tee": ("-filepath", "-path")}
PS_MOVERS = {"copy-item", "move-item", "copy", "move", "cpi", "mi", "cp", "mv"}
IN_PLACE = {"sed -i", "perl -i", "a script body", "a script file"}   # writes that change a file in places


@dataclass(frozen=True)
class Write:
    target: str
    how: str
    cwd: Path | None             # where a relative target resolves, None after a cd io-guard cannot follow


CHANGE_DIRECTORY = {"cd", "pushd", "set-location", "sl", "push-location", "chdir"}


def moved_to(simple: shell.SimpleCommand, cwd: Path | None, ctx: Context) -> Path | None:
    """The working directory after a cd, or None when io-guard cannot say where it went."""
    arguments = [word for word in simple.words[1:] if not word.startswith("-")]
    if len(arguments) != 1:
        return None
    return resolve(arguments[0], cwd, ctx)


@dataclass(frozen=True)
class Script:
    """A script file an interpreter runs in the command, as it reads now."""
    path: Path
    body: str
    arguments: tuple[str, ...]
    cwd: Path | None


def located(simples: tuple[shell.SimpleCommand, ...], event: Event,
            ctx: Context) -> list[tuple[shell.SimpleCommand, Path | None]]:
    """Each simple command with the folder it runs in, following each cd, and leaving the cds out."""
    found, cwd = [], event.cwd
    for simple in simples:
        if simple.name in CHANGE_DIRECTORY:
            cwd = moved_to(simple, cwd, ctx)
        else:
            found.append((simple, cwd))
    return found


def script_files(command: str, event: Event, ctx: Context) -> list[Script]:
    """The script files the command's interpreters run, up to SCRIPT_BYTES each, that can be read."""
    scripts = []
    for simple, cwd in located(shell.commands(command), event, ctx):
        run = shell.script_run(simple)
        path = None if run is None else resolve(run.script, cwd, ctx)
        if path is None:
            continue
        try:
            data = ctx.fs.read_bytes(path, SCRIPT_BYTES + 1)
        except OSError:
            continue
        if len(data) <= SCRIPT_BYTES:
            scripts.append(Script(path, data.decode("utf-8", "replace"), run.arguments, cwd))
    return scripts


def bash_writes(command: str, event: Event, ctx: Context) -> list[Write]:
    found = shell.scan(command)
    writes = []
    interpreter, script_cwd = False, event.cwd
    for simple, cwd in located(shell.commands(command, found), event, ctx):
        writes += [Write(redirect.target, "a > redirect", cwd) for redirect in simple.redirects]
        arguments = [word for word in simple.words[1:] if not word.startswith("-")]
        if simple.name in ("sed", "perl") and any(re.match(r"^-[a-zA-Z]*i|^--in-place", word)
                                                  for word in simple.words[1:]):
            files = sed_files(simple.words[1:]) if simple.name == "sed" else arguments[1:]
            writes += [Write(target, f"{simple.name} -i", cwd) for target in files]
        elif simple.name == "tee":
            writes += [Write(target, "tee", cwd) for target in arguments]
        elif simple.name in ("cp", "mv") and len(arguments) >= 2:
            writes.append(Write(arguments[-1], simple.name, cwd))
        elif shell.INTERPRETERS.match(simple.name) and not interpreter:
            interpreter, script_cwd = True, cwd
    bodies = [heredoc.body for heredoc in found.heredocs] if interpreter else []
    bodies += [body.body for body in found.bodies]
    bodies += moved_bodies(command, ctx)
    writes += [Write(target, "a script body", script_cwd)
               for body in bodies for target in script_targets(body)]
    writes += [Write(target, "a script file", script.cwd)
               for script in script_files(command, event, ctx) for target in script_targets(script.body)]
    return writes


def sed_files(arguments: list[str]) -> list[str]:
    """The files sed edits: its non-option words, less the script when no -e or -f gave one."""
    files, script_given, skip = [], False, False
    for word in arguments:
        if skip:
            skip = False
        elif word in ("-e", "-f", "--expression", "--file"):
            script_given, skip = True, True
        elif word.startswith(("--expression=", "--file=")):
            script_given = True
        elif not word.startswith("-"):
            files.append(word)
    return files if script_given else files[1:]


def moved_bodies(command: str, ctx: Context) -> list[str]:
    """The bodies transport.body moved into files that this command runs."""
    bodies = []
    for path in shell.body_files(command):
        try:
            bodies.append(ctx.fs.read_bytes(Path(path)).decode("utf-8", "replace"))
        except OSError:
            continue
    return bodies


def script_targets(body: str) -> list[str]:
    return [match["open"] or match["path"] or match["node"] for match in SCRIPT_WRITE.finditer(body)]


def powershell_writes(command: str, event: Event, ctx: Context) -> list[Write]:
    writes, cwd = [Write(target, "[IO.File]", event.cwd) for target in pwsh.file_calls(command)], event.cwd
    for simple in pwsh.commands(command):
        name, arguments = simple.name, list(simple.words[1:])
        if name in CHANGE_DIRECTORY:
            cwd = moved_to(simple, cwd, ctx)
            continue
        writes += [Write(redirect.target, "a > redirect", cwd) for redirect in simple.redirects]
        if name in PS_WRITERS:
            target = named(arguments, PS_WRITERS[name]) or positional(arguments)
            if target:
                writes.append(Write(target, simple.words[0], cwd))
        elif name in PS_MOVERS:
            target = named(arguments, ("-destination",))
            others = [word for word in arguments if not word.startswith("-")]
            target = target or (others[1] if len(others) >= 2 else None)
            if target:
                writes.append(Write(target, simple.words[0], cwd))
    return writes


def named(arguments: list[str], names: tuple[str, ...]) -> str | None:
    for index, word in enumerate(arguments[:-1]):
        if word.lower() in names:
            return arguments[index + 1]
    return None


def positional(arguments: list[str]) -> str | None:
    skip = False
    for word in arguments:
        if skip:
            skip = False
        elif word.startswith("-"):
            skip = word.lower() in ("-value", "-encoding", "-inputobject", "-width")
        else:
            return word
    return None


def resolve(raw: str, cwd: Path | None, ctx: Context) -> Path | None:
    """The path a write names, or None for a device, a variable, a wildcard, an empty word, or a relative
    path after a cd io-guard could not follow."""
    raw = raw.strip()
    if not raw or raw.lower() in DEVICES or re.search(r"[$`*?%]", raw):
        return None
    if raw.startswith("~"):
        home = ctx.env.get("USERPROFILE") or ctx.env.get("HOME")
        if not home:
            return None
        raw = home + raw[1:]
    if ctx.platform.windows and (drive := re.match(r"^/([a-zA-Z])(/|$)", raw)):
        raw = f"{drive[1].upper()}:/{raw[3:]}"
    absolute = re.match(r"^(?:[A-Za-z]:)?[\\/]", raw)
    if cwd is None and not absolute:
        return None
    return paths.normalise(raw, cwd or Path("/"), ctx.platform)


def tracked(path: Path, ctx: Context) -> bool | None:
    """Whether git tracks path, asked once per session. None when git cannot say."""
    with ctx.session.lock:
        if path in ctx.session.tracked:
            return ctx.session.tracked[path]
    try:
        answer = ctx.git.root(path) is not None and ctx.git.is_tracked(path)
    except GitError:
        return None
    with ctx.session.lock:
        ctx.session.tracked[path] = answer
    return answer


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
        tools=frozenset({Tool.BASH, Tool.POWERSHELL}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.REFUSED, cost=Cost.EXPENSIVE, reads=frozenset({"command"}), writes=frozenset(),
        after=frozenset(), config={}, codes=frozenset({Code.SHELL_WRITE}),
        description="Refuses a shell command that writes a file git tracks, and names the tool that writes "
                    "it safely.")

    def run(self, event: Event, ctx: Context) -> Decision:
        command = event.command or ""
        writer = powershell_writes if event.tool is Tool.POWERSHELL else bash_writes
        refusals, warnings = [], []
        for write in writer(command, event, ctx):
            path = resolve(write.target, write.cwd, ctx)
            if path is None or inside(path, event.scratchpad):
                continue
            state = tracked(path, ctx)
            if state:
                refusals.append(self.refusal(write, path, event, ctx))
            elif state is False and path.suffix.lower() in SCRIPT_SUFFIXES and self.in_repository(path, ctx):
                warnings.append(self.warning(path, event, ctx))
        if event.tool is not Tool.POWERSHELL:
            warnings += [found for script in script_files(command, event, ctx)
                         if (found := self.given(script, event, ctx)) is not None]
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
        if write.how in IN_PLACE:
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
            path = None if word.startswith("-") else resolve(word, script.cwd, ctx)
            if path is None or inside(path, event.scratchpad) or not tracked(path, ctx):
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
