"""The files a shell command writes, and the folder each of its commands runs in.

A write is a >, >>, >| or >&file redirect, an in-place edit by sed, gsed, perl, ruby or awk -i inplace,
alone, after env, or run by find -exec or xargs on the files of a folder, tee, cp and mv, a string bash -c or
pwsh -Command runs, a heredoc, python -c or node -e body that opens a file for writing, a body transport.body
moved into a file, a script file an interpreter runs, and PowerShell's Set-Content, Add-Content,
Clear-Content, Out-File, New-Item with -Value or -Force, Copy-Item, Move-Item, Tee-Object and [IO.File]
calls. A * or ? in a target's last name is matched against its folder, as the shell expands it. A cd inside
( ) holds for that subshell, and popd goes back to the folder pushd left. A target built from a variable, or
named after a cd that cannot be followed, has no path. A stream redirect such as 2>&1 writes no file (SHW-8).
A command's words inside a script body's string are data, not a write (GRD-1).
"""
import fnmatch
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from ioguard.lib import paths, pwsh, rules, shell
from ioguard.lib.context import Context
from ioguard.lib.platform import Platform
from ioguard.lib.ports import FsPort
from ioguard.lib.program import program_name

DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "nul", "$null", "con"}
SCRIPT_BYTES = 1024 * 1024       # a script file past this is not read
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
PS_SWITCHES = {"-force", "-nonewline", "-append", "-passthru", "-whatif", "-confirm", "-noclobber",
               "-asbytestream", "-verbose", "-debug", "-recurse"}   # the writers' options that take no value
PS_MOVERS = {"copy-item", "move-item", "copy", "move", "cpi", "mi", "cp", "mv"}
XARGS_VALUED = {"-n", "-I", "-d", "-P", "-L", "-s", "-E", "-a"}
CHANGE_DIRECTORY = {"cd", "pushd", "set-location", "sl", "push-location", "chdir"}
PUSH_DIRECTORY = {"pushd", "push-location"}
POP_DIRECTORY = {"popd", "pop-location"}


@dataclass(frozen=True)
class Host:
    """What placing a shell word reads: the platform, the environment that names ~, and the file system."""
    platform: Platform
    env: Mapping[str, str]
    fs: FsPort

    @classmethod
    def of(cls, ctx: Context) -> Host:
        return cls(ctx.platform, ctx.env, ctx.fs)


@dataclass(frozen=True)
class Write:
    target: str
    how: str
    cwd: Path | None             # where a relative target resolves, None after a cd that cannot be followed


@dataclass(frozen=True)
class Script:
    """A script file an interpreter runs in the command, as it reads now."""
    path: Path
    body: str
    arguments: tuple[str, ...]
    cwd: Path | None


def resolve(raw: str, cwd: Path | None, host: Host) -> Path | None:
    """The path a write names, or None for a device, a variable, a wildcard, an empty word, or a relative
    path after a cd that cannot be followed."""
    raw = raw.strip()
    if not raw or raw.lower() in DEVICES or re.search(r"[$`*?%]", raw):
        return None
    if raw.startswith("~"):
        home = host.env.get("USERPROFILE") or host.env.get("HOME")
        if not home:
            return None
        raw = home + raw[1:]
    if host.platform.windows and (drive := re.match(r"^/([a-zA-Z])(/|$)", raw)):
        raw = f"{drive[1].upper()}:/{raw[3:]}"
    absolute = re.match(r"^(?:[A-Za-z]:)?[\\/]", raw)
    if cwd is None and not absolute:
        return None
    return paths.normalise(raw, cwd or Path("/"), host.platform)


def moved_to(simple: shell.SimpleCommand, cwd: Path | None, host: Host) -> Path | None:
    """The working directory after a cd, or None when it cannot be said where it went."""
    arguments = [word for word in simple.words[1:] if not word.startswith("-")]
    if len(arguments) != 1:
        return None
    return resolve(arguments[0], cwd, host)


def located(command: str, start: Path | None, host: Host) -> list[tuple[shell.SimpleCommand, Path | None]]:
    """Each simple command with the folder it runs in, following each cd, pushd and popd, and leaving them
    out. A cd inside ( ) holds for that subshell only."""
    group_of, parent = shell.subshells(command, shell.scan(command))
    cwd_of: dict[int, Path | None] = {0: start}
    pushed: list[Path | None] = []
    placed = []
    for simple in shell.commands(command):
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
            cwd_of[group] = moved_to(simple, cwd_of[group], host)
        else:
            placed.append((simple, cwd_of[group]))
    return placed


def script_files(command: str, cwd: Path | None, host: Host) -> list[Script]:
    """The script files the command's interpreters run, up to SCRIPT_BYTES each, that can be read."""
    scripts = []
    for simple, where in located(command, cwd, host):
        run = shell.script_run(simple)
        path = None if run is None else resolve(run.script, where, host)
        if path is None:
            continue
        try:
            data = host.fs.read_bytes(path, SCRIPT_BYTES + 1)
        except OSError:
            continue
        if len(data) <= SCRIPT_BYTES:
            scripts.append(Script(path, data.decode("utf-8", "replace"), run.arguments, where))
    return scripts


def bash_writes(command: str, cwd: Path | None, host: Host, start: Path | None = None, depth: int = 0,
                scripts: list[Script] | None = None) -> list[Write]:
    """Every write the Bash command run from cwd makes. start is the folder a nested shell string runs in,
    when it is known, and scripts are the command's script files when the caller read them already."""
    found = shell.scan(command)
    writes: list[Write] = []
    interpreter, script_cwd = False, start or cwd
    for simple, where in located(command, start or cwd, host):
        writes += command_writes(simple, where, cwd, host, depth)
        words = run_words(simple)
        if not interpreter and words and shell.INTERPRETERS.match(program_name(words[0])):
            interpreter, script_cwd = True, where
    bodies = [heredoc.body for heredoc in found.heredocs] if interpreter else []
    bodies += [body.body for body in found.bodies] + moved_bodies(command, host)
    writes += [Write(target, "a script body", script_cwd)
               for body in bodies for target in script_targets(body)]
    scripts = script_files(command, cwd, host) if scripts is None else scripts
    writes += [Write(target, "a script file", script.cwd)
               for script in scripts for target in script_targets(script.body)]
    # A python -c body is read by its program above and by the scan, which also finds one inside $().
    return list(dict.fromkeys(writes))


def run_words(simple: shell.SimpleCommand) -> list[str]:
    """The words of the program a simple command runs, less env and the wrappers such as timeout."""
    return rules.unwrapped(without_env(list(simple.words)))


def command_writes(simple: shell.SimpleCommand, where: Path | None, cwd: Path | None, host: Host,
                   depth: int) -> list[Write]:
    """The writes of one simple command that runs in where. cwd is the whole command's folder, which a shell
    string the simple command runs falls back to when where is unknown."""
    writes = [Write(redirect.target, "a > redirect", where) for redirect in simple.redirects]
    words = run_words(simple)
    name = program_name(words[0]) if words else ""
    wrapped = rules.wrapped(words)
    if (under := delegated(without_env(list(simple.words)))) is not None:
        return writes + delegated_writes(under, where)
    if (edited := in_place(words)) is not None:
        return writes + [Write(target, edited[0], where) for target in edited[1]]
    if name == "tee":
        return writes + [Write(target, "tee", where) for target in words[1:] if not target.startswith("-")]
    if name in ("cp", "mv"):
        return writes + [Write(target, name, where) for target in landed(words[1:], where, host)]
    if wrapped is not None and wrapped.text is not None and depth < rules.NESTED:
        reader = bash_writes if wrapped.dialect is rules.Dialect.BASH else powershell_writes
        return writes + reader(wrapped.text, cwd, host, where, depth + 1)
    if wrapped is not None and wrapped.text is None and wrapped.raw:
        return writes + [Write(target, "a script body", where) for target in script_targets(wrapped.raw)]
    return writes


def delegated_writes(under: tuple[list[str], list[str], str], where: Path | None) -> list[Write]:
    """The files find -exec or xargs edits in place: the files the inner command names, or the folders the
    files come from when it names them only as {}."""
    inner, roots, how = under
    edited = in_place(inner)
    if edited is None:
        return []
    files = [target for target in edited[1] if target != "{}"]
    return [Write(target, f"{edited[0]} under {how}", where) for target in files or roots]


def without_env(words: list[str]) -> list[str]:
    """words without a leading env and its options and settings."""
    if words[:1] == ["env"]:
        words = words[1:]
        while words and (words[0].startswith("-") or shell.ASSIGNMENT.match(words[0])):
            words = words[1:]
    return words


def in_place(words: list[str]) -> tuple[str, list[str]] | None:
    """How words edit files in place, such as sed -i, and the files they edit, or None when they do not."""
    if not words:
        return None
    name, flags = program_name(words[0]), words[1:]
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
    name = program_name(words[0]) if words else ""
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


def landed(words: list[str], cwd: Path | None, host: Host) -> list[str]:
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
        if not into_folder(target, cwd, host):
            return [target]
        folder = target
    return [inside_folder(folder, source) for source in operands]


def into_folder(raw: str, cwd: Path | None, host: Host) -> bool:
    """Whether a copy or move names a folder to put its sources in, by a trailing slash or on disk."""
    if raw.endswith(("/", "\\")):
        return True
    path = resolve(raw, cwd, host)
    return path is not None and host.fs.is_dir(path)


def inside_folder(folder: str, source: str) -> str:
    """The path a source lands at in folder: the folder, then the source's own last name."""
    return f"{folder.rstrip('/\\')}/{PureWindowsPath(source.rstrip('/\\')).name}"


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


def moved_bodies(command: str, host: Host) -> list[str]:
    """The bodies transport.body moved into files that this command runs."""
    bodies = []
    for path in shell.body_files(command):
        try:
            bodies.append(host.fs.read_bytes(Path(path)).decode("utf-8", "replace"))
        except OSError:
            continue
    return bodies


def script_targets(body: str) -> list[str]:
    return [match["open"] or match["path"] or match["node"] for match in SCRIPT_WRITE.finditer(body)]


def powershell_writes(command: str, cwd: Path | None, host: Host, start: Path | None = None,
                      depth: int = 0) -> list[Write]:
    """Every write the PowerShell command run from cwd makes. start is the folder a nested shell string runs
    in, when it is known."""
    where = start or cwd
    writes, pushed = [Write(target, "[IO.File]", where) for target in pwsh.file_calls(command)], []
    for simple in pwsh.commands(command):
        name, arguments = simple.name, list(simple.words[1:])
        if name in POP_DIRECTORY:
            where = pushed.pop() if pushed else None
            continue
        if name in CHANGE_DIRECTORY:
            if name in PUSH_DIRECTORY:
                pushed.append(where)
            where = moved_to(simple, where, host)
            continue
        writes += [Write(redirect.target, "a > redirect", where) for redirect in simple.redirects]
        lowered = [word.lower().split(":", 1)[0] for word in arguments]
        creates = name in PS_CREATORS and ("-value" in lowered or "-force" in lowered)
        if name in PS_WRITERS or creates:
            target = named(arguments, PS_WRITERS.get(name, ("-path",))) or positional(arguments)
            if target:
                writes.append(Write(target, simple.words[0], where))
        elif name in PS_MOVERS:
            target = named(arguments, ("-destination",))
            others = [word for word in arguments if not word.startswith("-") and word != target]
            source = named(arguments, ("-path", "-literalpath")) or (others[0] if others else None)
            target = target or (others[1] if len(others) >= 2 else None)
            if target and source and into_folder(target, where, host):
                target = inside_folder(target, source)
            if target:
                writes.append(Write(target, simple.words[0], where))
    if depth < rules.BLOCKS:
        for block in pwsh.script_blocks(command):
            writes += powershell_writes(block, cwd, host, start, depth + 1)
    # An [IO.File] call inside a block is found in the whole command and again in its block.
    return list(dict.fromkeys(writes))


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
    """The first argument no option takes: an option takes the word after it unless it is a switch, or
    gives its value after a colon, as -Confirm:$false does."""
    skip = False
    for word in arguments:
        if skip:
            skip = False
        elif word.startswith("-"):
            skip = ":" not in word and word.lower() not in PS_SWITCHES
        else:
            return word
    return None


def targets(write: Write, host: Host) -> list[Path]:
    """The files a write lands on: its target, or each file in the target's folder that a * or ? in its last
    name matches, as the shell expands it."""
    raw = write.target.strip()
    folder, _, name = raw.replace("\\", "/").rpartition("/")
    if not re.search(r"[*?]", name) or re.search(r"[$`*?%]", folder):
        path = resolve(raw, write.cwd, host)
        return [] if path is None else [path]
    base = resolve(folder or ".", write.cwd, host)
    if base is None:
        return []
    fold = host.platform.case_insensitive
    return [path for path in host.fs.list_dir(base)
            if fnmatch.fnmatchcase(path.name.lower() if fold else path.name, name.lower() if fold else name)]
