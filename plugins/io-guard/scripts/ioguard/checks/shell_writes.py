"""Refuse a shell command that writes a file git tracks, and name the tool that writes it safely.

A write through the shell skips io-guard's byte checks and Claude Code's checkpoints (SHW-1). The check finds
each write a command makes: a >, >>, >| or >&file redirect, an in-place edit by sed, gsed, perl, ruby or awk
-i inplace, alone, after env, or run by find -exec or xargs on the files of a folder, tee, cp and mv, a
string bash -c or pwsh -Command runs, a heredoc, python -c or node -e body that opens a file for writing, a
body transport.body moved into a file, a script file an interpreter runs, and PowerShell's Set-Content,
Add-Content, Clear-Content, Out-File, New-Item with -Value or -Force, Copy-Item, Move-Item, Tee-Object and
[IO.File] calls. A * or ? in a target's last name is matched against its folder, as the shell expands it. A
cd inside ( ) holds for that subshell, and popd goes back to the folder pushd left. The check refuses a
write only when git tracks its target, and the refusal of an in-place edit, such as sed -i or a script body,
names io.edit, which makes several changes in one call. A write to the scratchpad, to a device, or outside any
repository passes. A target built from a variable, or named after a cd the check cannot follow, passes too.
Git's answer for a path holds for the session until a command names git, which can add or remove a file.
A script file that writes to a path it does not spell out, given a tracked file, gets a warning that names
io.edit, or io.format when it runs a formatter. A script file the shell creates inside a repository gets a
warning that points at the scratchpad (GIT-1). A
stream redirect such as 2>&1 writes no file (SHW-8). A command's words inside a script body's string are
data, not a write (GRD-1).
"""
import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import paths, pwsh, rules, shell
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
              "tee": ("-filepath", "-path"), "clear-content": ("-path", "-literalpath"),
              "clc": ("-path", "-literalpath")}
PS_CREATORS = {"new-item", "ni"}          # a writer when it gives -Value, or -Force, which empties a file
PS_MOVERS = {"copy-item", "move-item", "copy", "move", "cpi", "mi", "cp", "mv"}
IN_PLACE = {"a script body", "a script file"}   # with every ... -i, writes that change a file in places
XARGS_VALUED = {"-n", "-I", "-d", "-P", "-L", "-s", "-E", "-a"}
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
RUNS_GIT = re.compile(r"(?<![\w.-])git(?:\.exe)?(?=\s|$)", re.I)


@dataclass(frozen=True)
class Write:
    target: str
    how: str
    cwd: Path | None             # where a relative target resolves, None after a cd io-guard cannot follow


CHANGE_DIRECTORY = {"cd", "pushd", "set-location", "sl", "push-location", "chdir"}
PUSH_DIRECTORY = {"pushd", "push-location"}
POP_DIRECTORY = {"popd", "pop-location"}


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


def located(command: str, found: shell.Scan, start: Path | None,
            ctx: Context) -> list[tuple[shell.SimpleCommand, Path | None]]:
    """Each simple command with the folder it runs in, following each cd, pushd and popd, and leaving them
    out. A cd inside ( ) holds for that subshell only."""
    group_of, parent = shell.subshells(command, found.states)
    cwd_of: dict[int, Path | None] = {0: start}
    pushed: list[Path | None] = []
    placed = []
    for simple in shell.commands(command, found):
        group = group_of[simple.span[0]] if simple.span[0] < len(group_of) else 0
        if group not in cwd_of:
            chain = [group]
            while chain[-1] not in cwd_of:
                chain.append(parent[chain[-1]])
            for each in reversed(chain[:-1]):
                cwd_of[each] = cwd_of[parent[each]]
        if simple.name in POP_DIRECTORY:
            cwd_of[group] = pushed.pop() if pushed else None
        elif simple.name in CHANGE_DIRECTORY:
            if simple.name in PUSH_DIRECTORY:
                pushed.append(cwd_of[group])
            cwd_of[group] = moved_to(simple, cwd_of[group], ctx)
        else:
            placed.append((simple, cwd_of[group]))
    return placed


def script_files(command: str, event: Event, ctx: Context) -> list[Script]:
    """The script files the command's interpreters run, up to SCRIPT_BYTES each, that can be read."""
    scripts = []
    for simple, cwd in located(command, shell.scan(command), event.cwd, ctx):
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


def bash_writes(command: str, event: Event, ctx: Context, start: Path | None = None, depth: int = 0,
                scripts: list[Script] | None = None) -> list[Write]:
    """Every write the Bash command makes. scripts are its script files when the caller read them already."""
    found = shell.scan(command)
    writes = []
    interpreter, script_cwd = False, start or event.cwd
    bodies: list[str] = []
    for simple, cwd in located(command, found, start or event.cwd, ctx):
        writes += [Write(redirect.target, "a > redirect", cwd) for redirect in simple.redirects]
        under = delegated(without_env(list(simple.words)))
        words = rules.unwrapped(without_env(list(simple.words)))
        name = shell.SimpleCommand(tuple(words), (), (), simple.span).name if words else ""
        arguments = [word for word in words[1:] if not word.startswith("-")]
        edited = None if under is not None else in_place(words)
        wrapped = rules.wrapped(words)
        if shell.INTERPRETERS.match(name) and not interpreter:
            interpreter, script_cwd = True, cwd
        if edited is not None:
            writes += [Write(target, edited[0], cwd) for target in edited[1]]
        elif under is not None:
            inner, roots, how = under
            if (edited := in_place(inner)) is not None:
                files = [target for target in edited[1] if target != "{}"]
                writes += [Write(target, f"{edited[0]} under {how}", cwd) for target in files or roots]
        elif name == "tee":
            writes += [Write(target, "tee", cwd) for target in arguments]
        elif name in ("cp", "mv"):
            writes += [Write(target, name, cwd) for target in landed(words[1:], cwd, ctx)]
        elif wrapped is not None and wrapped.text is not None and depth < rules.NESTED:
            reader = bash_writes if wrapped.dialect == "bash" else powershell_writes
            writes += reader(wrapped.text, event, ctx, cwd, depth + 1)
        elif wrapped is not None and wrapped.text is None and wrapped.raw:
            writes += [Write(target, "a script body", cwd) for target in script_targets(wrapped.raw)]
    bodies += [heredoc.body for heredoc in found.heredocs] if interpreter else []
    bodies += [body.body for body in found.bodies]
    bodies += moved_bodies(command, ctx)
    writes += [Write(target, "a script body", script_cwd)
               for body in bodies for target in script_targets(body)]
    scripts = script_files(command, event, ctx) if scripts is None else scripts
    writes += [Write(target, "a script file", script.cwd)
               for script in scripts for target in script_targets(script.body)]
    return writes


def without_env(words: list[str]) -> list[str]:
    """words without a leading env and its options and settings."""
    if words[:1] == ["env"]:
        words = words[1:]
        while words and (words[0].startswith("-") or ASSIGNMENT.match(words[0])):
            words = words[1:]
    return words


def in_place(words: list[str]) -> tuple[str, list[str]] | None:
    """How words edit files in place, such as sed -i, and the files they edit, or None when they do not."""
    if not words:
        return None
    name, flags = words[0].rsplit("/", 1)[-1].lower().removesuffix(".exe"), words[1:]
    if name in ("sed", "gsed") and any(re.match(r"^-[a-zA-Z]*[iI]|^--in-place", word) for word in flags):
        return f"{name} -i", sed_files(flags)
    if name in ("perl", "ruby") and any(re.match(r"^-[a-zA-Z0-9]*i", word) for word in flags):
        return f"{name} -i", code_files(flags)
    if name in ("awk", "gawk") and ("inplace" in flags or "--include=inplace" in flags):
        rest = [word for word in flags if word not in ("-i", "inplace", "--include=inplace")]
        return f"{name} -i inplace", [word for word in rest if not word.startswith("-")][1:]
    return None


def code_files(flags: list[str]) -> list[str]:
    """The files a perl or ruby -i edits: its operands, less the code an -e gave or the first operand."""
    files, code_given, skip = [], False, False
    for word in flags:
        if skip:
            skip = False
        elif word == "-e":
            code_given, skip = True, True
        elif not word.startswith("-"):
            files.append(word)
    return files if code_given else files[1:]


def delegated(words: list[str]) -> tuple[list[str], list[str], str] | None:
    """The command find -exec or xargs runs on each file, the folders the files come from, and which of the
    two it is. None for any other command. xargs reads its files from stdin, so its folder is ".", the one it
    runs in."""
    name = words[0].rsplit("/", 1)[-1].lower() if words else ""
    if name == "find":
        at = next((index for index, word in enumerate(words) if word in ("-exec", "-execdir", "-ok")), None)
        if at is None:
            return None
        roots = []
        for word in words[1:]:
            if word.startswith(("-", "(", "!")):
                break
            roots.append(word)
        inner = []
        for word in words[at + 1:]:
            if word in (";", "+", "\\;"):
                break
            inner.append(word)
        return inner, roots or ["."], "find -exec"
    if name == "xargs":
        rest, index = words[1:], 0
        while index < len(rest) and rest[index].startswith("-"):
            index += 2 if rest[index] in XARGS_VALUED else 1
        return rest[index:], ["."], "xargs"
    return None


def landed(words: list[str], cwd: Path | None, ctx: Context) -> list[str]:
    """The files a cp or mv writes: its last argument, or each source's name inside the folder it names, by
    -t, by a trailing slash, or by being a folder on disk."""
    folder, operands, given = None, [], iter(words)
    for word in given:
        if word in ("-t", "--target-directory"):
            folder = next(given, None)
        elif word.startswith("--target-directory="):
            folder = word.split("=", 1)[1]
        elif not word.startswith("-"):
            operands.append(word)
    if folder is None:
        if len(operands) < 2:
            return []
        *operands, target = operands
        if not into_folder(target, cwd, ctx):
            return [target]
        folder = target
    return [inside_folder(folder, source) for source in operands]


def into_folder(raw: str, cwd: Path | None, ctx: Context) -> bool:
    """Whether a copy or move names a folder to put its sources in, by a trailing slash or on disk."""
    if raw.endswith(("/", "\\")):
        return True
    path = resolve(raw, cwd, ctx)
    return path is not None and ctx.fs.is_dir(path)


def inside_folder(folder: str, source: str) -> str:
    """The path a source lands at in folder: the folder, then the source's own last name."""
    return f"{folder.rstrip('/\\')}/{re.split(r'[\\/]', source.rstrip('/\\'))[-1]}"


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


def powershell_writes(command: str, event: Event, ctx: Context, start: Path | None = None,
                      depth: int = 0) -> list[Write]:
    cwd = start or event.cwd
    writes, pushed = [Write(target, "[IO.File]", cwd) for target in pwsh.file_calls(command)], []
    for simple in pwsh.commands(command):
        name, arguments = simple.name, list(simple.words[1:])
        if name in POP_DIRECTORY:
            cwd = pushed.pop() if pushed else None
            continue
        if name in CHANGE_DIRECTORY:
            if name in PUSH_DIRECTORY:
                pushed.append(cwd)
            cwd = moved_to(simple, cwd, ctx)
            continue
        writes += [Write(redirect.target, "a > redirect", cwd) for redirect in simple.redirects]
        lowered = [word.lower().split(":", 1)[0] for word in arguments]
        creates = name in PS_CREATORS and ("-value" in lowered or "-force" in lowered)
        if name in PS_WRITERS or creates:
            target = named(arguments, PS_WRITERS.get(name, ("-path",))) or positional(arguments)
            if target:
                writes.append(Write(target, simple.words[0], cwd))
        elif name in PS_MOVERS:
            target = named(arguments, ("-destination",))
            others = [word for word in arguments if not word.startswith("-") and word != target]
            source = named(arguments, ("-path", "-literalpath")) or (others[0] if others else None)
            target = target or (others[1] if len(others) >= 2 else None)
            if target and source and into_folder(target, cwd, ctx):
                target = inside_folder(target, source)
            if target:
                writes.append(Write(target, simple.words[0], cwd))
    return writes


def named(arguments: list[str], names: tuple[str, ...]) -> str | None:
    """The value of the first of names among arguments, given as -Path value or as -Path:value."""
    for index, word in enumerate(arguments):
        flag, colon, value = word.partition(":")
        if flag.lower() in names:
            if colon:
                return value
            if index + 1 < len(arguments):
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


def targets(write: Write, ctx: Context) -> list[Path]:
    """The files a write lands on: its target, or each file in the target's folder that a * or ? in its last
    name matches, as the shell expands it."""
    raw = write.target.strip()
    folder, _, name = raw.replace("\\", "/").rpartition("/")
    if not re.search(r"[*?]", name) or re.search(r"[$`*?%]", folder):
        path = resolve(raw, write.cwd, ctx)
        return [] if path is None else [path]
    base = resolve(folder or ".", write.cwd, ctx)
    if base is None:
        return []
    fold = ctx.platform.case_insensitive
    return [path for path in ctx.fs.list_dir(base)
            if fnmatch.fnmatchcase(path.name.lower() if fold else path.name, name.lower() if fold else name)]


def tracked(path: Path, ctx: Context) -> bool | None:
    """Whether git tracks path, asked once per session until the session runs a git command. None when git
    cannot say."""
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
        if RUNS_GIT.search(command):
            with ctx.session.lock:
                ctx.session.tracked.clear()
        bash = event.tool is not Tool.POWERSHELL
        scripts = script_files(command, event, ctx) if bash else []
        found = (bash_writes(command, event, ctx, scripts=scripts) if bash
                 else powershell_writes(command, event, ctx))
        refusals, warnings = [], []
        for write in found:
            for path in targets(write, ctx):
                if inside(path, event.scratchpad):
                    continue
                state = tracked(path, ctx)
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
