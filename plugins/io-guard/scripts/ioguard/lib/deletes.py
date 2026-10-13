"""The files and folders a shell command deletes, and the real paths each target names before it runs.

A delete is rm, rmdir or unlink, alone, after a wrapper such as sudo, exec, command or busybox, or run by
find -exec or xargs; a bash -c, sh -c or eval string, a $( ) or backtick part, a heredoc or here-string a
shell reads, that holds one; PowerShell's Remove-Item and its aliases rm, ri, del, erase, rd and rmdir,
[IO.Directory]::Delete and [IO.File]::Delete, in a script block or an Invoke-Expression string too; cmd /c
or //c del, erase, rd and rmdir; git clean with --force, and git rm without --cached. Some deletes name no
target before the command runs: xargs takes its targets from stdin, Remove-Item with no path takes them from
the pipeline, a shell fed by a pipe reads commands nobody wrote down, and a string nested past rules.NESTED
is not read. Each of those is a Delete with no target and the reason in unnamed.

A target resolves the way its shell expands it. Bash matches an unquoted * ? or [ against each folder, with
case and leaving out the names that start with a dot, unless the command turns on dotglob, nocaseglob,
globstar or GLOBIGNORE, when it matches every name without case. On Windows Git Bash shows a private-use
character U+F000 + c in a name as the ASCII character c, so a folder named C + U+F03A matches C? as C:. A
word Git Bash passes on is then a path again: a word that starts with a drive is that drive, /c/ is the
drive C:, /tmp is the temp folder, and every other : * ? " < > | in a name is the private-use character it
stands for. PowerShell matches its wildcards without case, unless the path is a -LiteralPath, and cmd
matches * and ? in the last name. A target that holds a variable, a command's output, a brace list or a
splatted table, starts with ~user, or names a Git Bash folder such as /usr or a PowerShell provider such as
HKCU:, has no path before the command runs, and Resolved says why.
"""
import fnmatch
import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from ioguard.lib import paths, pwsh, rules, shell
from ioguard.lib.program import program_name
from ioguard.lib.writes import (CHANGE_DIRECTORY, POP_DIRECTORY, PUSH_DIRECTORY, Host, located, moved_to,
                                without_env)

RM_PROGRAMS = frozenset({"rm", "rmdir", "unlink"})
REMOVE_ITEM = frozenset({"remove-item", "rm", "ri", "del", "erase", "rd", "rmdir"})
INVOKE_EXPRESSION = frozenset({"invoke-expression", "iex"})
CMD_DELETES = {"del": "/s", "erase": "/s", "rd": "/s", "rmdir": "/s"}   # each program, its recursive switch
CMD_DELETE_WORD = re.compile(r"(?<![\w.\\/:%-])(del|erase|rd|rmdir)(?=[\s/]|$)", re.I)
CMD_MOVES = re.compile(r"^\s*\(?\s*(?:cd|chdir|pushd|popd)(?=[\s/\\.]|$)", re.I)
PS_VALUED = ("-path", "-literalpath", "-lp", "-pspath", "-include", "-exclude", "-filter", "-credential",
             "-stream", "-erroraction", "-ea", "-warningaction", "-wa", "-informationaction", "-ia",
             "-errorvariable", "-ev", "-outvariable", "-ov", "-outbuffer", "-ob", "-pipelinevariable", "-pv",
             "-progressaction", "-proga", "-warningvariable", "-wv", "-informationvariable", "-iv")
SUDO_VALUED = frozenset({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "--user", "--group",
                         "--host", "--prompt", "--close-from", "--chdir", "--role", "--type", "--other-user",
                         "--command-timeout"})
XARGS_VALUED = frozenset({"-I", "-n", "-d", "-P", "-L", "-s", "-E", "-a"})
FIND_NAMING = frozenset({"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename"})
FIND_NARROWING = FIND_NAMING | {"-regex", "-iregex"}     # the tests that pick names, not ages or sizes
ONLY_VARIABLE = re.compile(r"\s*\$\{?\w+\}?\s*")
IO_LINK = re.compile(r"::Create(?:Symbolic|Hard)Link\(", re.I)
GLOB_LIMIT = 10_000              # the names a wildcard may examine before the target counts as unreadable
TOO_MANY = f"its wildcard reaches past {GLOB_LIMIT:,} names, more than io-guard checks before it runs"
GIT_VALUED = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
IO_DELETE = re.compile(r"\[(?:System\.)?IO\.(?P<kind>Directory|File)\]::Delete\(\s*(?P<path>'(?:[^']|'')*'"
                       r"|\"[^\"]*\"|[^,)]*?)\s*(?:,\s*(?P<recursive>[^)]*?)\s*)?\)", re.I)
DELETE_WORDS = re.compile(r"(?<![\w.-])(?:rm|rmdir|unlink|del|erase|rd|ri|remove-item|clean|delete|"
                          r"invoke-expression|iex)(?![\w-])", re.I)
WIDE_GLOB = re.compile(r"\bshopt\s+-s\b[^;&|\n]*\b(?:dotglob|nocaseglob|globstar)\b|\bGLOBIGNORE=")
EXTGLOB = re.compile(r"\bshopt\s+-s\b[^;&|\n]*\bextglob\b")
MAKES_LINK = re.compile(r"-(?:Item)?Type[:\s]\s*['\"]?(?:Junction|SymbolicLink|HardLink)\b", re.I)
NOT_FILES = re.compile(r"^(?:env|variable|function|alias):", re.I)   # PowerShell drives that hold no files
BRACE_LIST = re.compile(r"\{[^{}\s]*(?:,|\.\.)[^{}\s]*\}")
PROVIDER = re.compile(r"^[A-Za-z][A-Za-z0-9]+:|::")       # HKCU:, Env:, FileSystem::, never a drive letter
MSYS_MAPPED = ':*?"<>|'                                   # the names Git Bash keeps as U+F000 + c on disk
PRIVATE = 0xF000
Placed = list[tuple[shell.SimpleCommand, Path | None]]   # each simple command and the folder it runs in
LATER = "it holds a variable or a command's output, which has a value only when the command runs"
RELATIVE_LOST = "it is relative, after a cd io-guard cannot follow"


class Shell(Enum):
    BASH = "bash"
    POWERSHELL = "powershell"
    CMD = "cmd"


@dataclass(frozen=True)
class Delete:
    how: str                     # the command as a message names it, such as rm -rf or Remove-Item -Recurse
    target: str                  # the target as written, quotes kept, or "" when the delete names none
    recursive: bool
    shell: Shell
    cwd: Path | None             # where a relative target resolves, None after a cd that cannot be followed
    literal: bool = False        # PowerShell's -LiteralPath, which matches no wildcard
    wide: bool = False           # the command widens bash's wildcards to dot names and any case
    unnamed: str = ""            # why the delete names no target, such as xargs reading them from stdin


@dataclass(frozen=True)
class Resolved:
    paths: tuple[Path, ...]      # each absolute path the target names, no link followed
    unresolved: str = ""         # why the target has no path before the command runs, "" when it has
    globbed: bool = False        # a wildcard chose the paths


def unnamed(how: str, why: str, where: Path | None, shell_of: Shell = Shell.BASH) -> Delete:
    return Delete(how, "", True, shell_of, where, unnamed=why)


def unread(text: str, how: str, where: Path | None) -> list[Delete]:
    """A delete with no target for text nested past what io-guard reads, when it names a delete with its
    backslashes and quotes taken out, so a name built from parts, such as r\\m, still counts. shell.lint
    refuses a command nested deeper still."""
    named = DELETE_WORDS.search(re.sub(r"[\\'\"]", "", text))
    return [unnamed(how, "it nests deeper than io-guard reads", where)] if named else []


def makes_link(command: str, powershell: bool, depth: int = 0) -> bool:
    """Whether the command runs ln -s, mklink, junction or New-Item -ItemType Junction, SymbolicLink or
    HardLink, which can lead a path elsewhere by the time a later part of the same command deletes through
    it. A shell string it runs and a script block are read too; a word inside quotes or a heredoc is not."""
    if depth > rules.NESTED:
        return False
    for simple in pwsh.commands(command) if powershell else shell.commands(command):
        words, _, _ = unwrapped_further(rules.unwrapped(without_env(list(simple.words))), [], None)
        if not words:
            continue
        name = program_name(words[0]).lower()
        if name in ("mklink", "junction") or (name == "ln" and any(
                re.match(r"^-\w*s", word) or word == "--symbolic" for word in words[1:])):
            return True
        if name in ("new-item", "ni") and MAKES_LINK.search(" ".join(words[1:])):
            return True
        if powershell and IO_LINK.search(" ".join(words)):
            return True
        wrapped = rules.wrapped(words)
        if wrapped is not None and wrapped.what == "cmd /c" and re.search(r"(?i)\bmklink\b", wrapped.raw):
            return True
        if wrapped is not None and wrapped.text is not None and wrapped.dialect is not rules.Dialect.NONE \
                and makes_link(wrapped.text, wrapped.dialect is rules.Dialect.POWERSHELL, depth + 1):
            return True
    if powershell:
        return IO_LINK.search(command) is not None or any(makes_link(block, True, depth + 1)
                                                          for block in pwsh.script_blocks(command))
    return any(makes_link(inner, False, depth + 1) for _, inner in substitutions(command))


def bash_deletes(command: str, cwd: Path | None, host: Host, depth: int = 0) -> list[Delete]:
    """Every delete the Bash command run in cwd makes. cwd is None for a string that runs after a cd
    io-guard cannot follow."""
    placed = located(command, cwd, host)
    found: list[Delete] = []
    for simple, where in placed:
        found += simple_deletes(simple, where, host, depth, stripped_wrapper(command, simple))
    for at, inner in substitutions(command):
        found += nested_bash(inner, folder_at(at, placed, cwd), host, depth, "a $( ) part")
    found += stdin_shells(command, placed, host, depth)
    code = shell.blanked(command)
    if EXTGLOB.search(code):
        found = [replace(delete, unnamed="the command turns on extglob, whose patterns io-guard does not "
                                         "expand") for delete in found]
    elif WIDE_GLOB.search(code):
        found = [replace(delete, wide=True) for delete in found]
    return list(dict.fromkeys(found))


def nested_bash(text: str, where: Path | None, host: Host, depth: int, how: str) -> list[Delete]:
    """The deletes of a Bash string run in where, one with no target for a string that is only a variable,
    and one with no target past rules.NESTED."""
    if ONLY_VARIABLE.fullmatch(text):
        return [unnamed(how, "it runs a string held in a variable", where)]
    if depth + 1 > rules.NESTED:
        return unread(text, how, where)
    return bash_deletes(text, where, host, depth + 1)


def nested_powershell(text: str, where: Path | None, host: Host, depth: int, how: str) -> list[Delete]:
    if depth + 1 > rules.NESTED:
        return unread(text, how, where)
    return powershell_deletes(text, where, host, depth + 1)


def substitutions(command: str) -> list[tuple[int, str]]:
    """Where each outermost $( ) and backtick part of command starts, and its text, which bash runs before
    the command, those in a heredoc body bash expands included. An inner one is read when its outer one
    is."""
    scanned, found, reach = shell.scan(command), [], -1
    for at, end in sorted(scanned.closes.items()):
        if at < reach or not command.startswith("$(", at) or command.startswith("$((", at):
            continue
        found.append((at, command[at + 2:end - 1]))
        reach = end
    ticks = [at for at, char in enumerate(command)
             if char == "`" and scanned.states[at] in (shell.NORMAL, shell.DOUBLE)
             and not escaped(command, at)]
    found += [(start, command[start + 1:end]) for start, end in zip(ticks[::2], ticks[1::2])]
    for heredoc in scanned.heredocs:
        if not heredoc.quoted and heredoc.body != command:
            found += [(heredoc.span[0] + at, inner) for at, inner in substitutions(heredoc.body)]
    return found


def escaped(text: str, at: int) -> bool:
    """Whether an odd run of backslashes stands before offset at, so the character there is literal."""
    run = 0
    while at - run > 0 and text[at - run - 1] == "\\":
        run += 1
    return run % 2 == 1


def folder_at(at: int, placed: Placed, cwd: Path | None) -> Path | None:
    """The folder the simple command around offset at runs in, else the one before it, else cwd."""
    before = cwd
    for simple, where in placed:
        if simple.span[0] <= at <= simple.span[1]:
            return where
        if simple.span[0] < at:
            before = where
    return before


def stdin_shells(command: str, placed: Placed, host: Host, depth: int) -> list[Delete]:
    """The deletes of the heredocs and here-strings a shell with no command string or script reads, and one
    with no target when a pipe feeds it."""
    found: list[Delete] = []
    for simple, where in placed:
        words = rules.unwrapped(without_env(list(simple.words)))
        if not words or program_name(words[0]).lower() not in rules.SHELLS:
            continue
        if rules.wrapped(words) is not None or any(not word.startswith(("-", "+")) for word in words[1:]):
            continue
        bodies = [heredoc.body for heredoc in shell.scan(command).heredocs
                  if simple.span[0] <= heredoc.operator[0] <= simple.span[1]]
        for body in bodies + here_strings(command, simple.span):
            found += nested_bash(body, where, host, depth, "a shell reading its input")
        if fed_by_pipe(command, simple):
            found.append(unnamed(program_name(words[0]), "the shell reads its commands from a pipe", where))
    return found


def fed_by_pipe(command: str, simple: shell.SimpleCommand) -> bool:
    """Whether a | or |& outside quotes feeds the simple command its input."""
    before = command[:simple.span[0]].rstrip()
    if before.endswith("|&"):
        before = before[:-1]
    return before.endswith("|") and not before.endswith("||") and \
        shell.scan(command).states[len(before) - 1] == shell.NORMAL


def stripped_wrapper(command: str, simple: shell.SimpleCommand) -> str:
    """The last sudo, doas, exec or command among the reserved words and redirects that shell.split dropped
    from the head of simple, or "". Its options are still in the words, and some of them take the word after
    them, as -u does in nohup sudo -u root rm."""
    found = ""
    for token in command[simple.span[0]:simple.span[1]].split():
        if shell.ASSIGNMENT.match(token) or re.match(r"^\d*[<>&]", token):
            continue
        if token not in shell.WRAPPERS or simple.words[:1] == (token,):
            break
        if token in ("sudo", "doas", "exec", "command"):
            found = token
    return found


def here_strings(command: str, span: tuple[int, int]) -> list[str]:
    """The word of each <<< inside span of command, as bash passes it."""
    scanned, found = shell.scan(command), []
    for match in re.finditer(r"<<<[ \t]*", command):
        if scanned.states[match.start()] != shell.NORMAL or not span[0] <= match.start() <= span[1]:
            continue
        end = shell.word_end(command, scanned, match.end())
        found.append(shell.unquote(command, scanned.states, match.end(), end))
    return found


def simple_deletes(simple: shell.SimpleCommand, where: Path | None, host: Host, depth: int,
                   wrapper: str = "") -> list[Delete]:
    """The deletes of one simple command that runs in where, after the wrapper the parser dropped."""
    words = without_env(list(simple.words))
    raws = list(simple.raw[len(simple.words) - len(words):]) if simple.raw else list(words)
    if wrapper:
        words, raws = [wrapper, *words], [wrapper, *raws]
    peeled = rules.unwrapped(words)
    if any(program_name(word) == "xargs" for word in words[:len(words) - len(peeled) + 1]):
        start = [program_name(word) for word in words].index("xargs") + 1
        return xargs_deletes(words[start:], where, host, depth)
    peeled, raws, where = unwrapped_further(peeled, raws[len(raws) - len(peeled):], where)
    if not peeled:
        return []
    name = program_name(peeled[0])
    if name == "xargs":
        return xargs_deletes(peeled[1:], where, host, depth)
    if name in RM_PROGRAMS:
        return rm_deletes(name, peeled[1:], raws[1:], where)
    if name == "find":
        return find_deletes(peeled, raws, where, host, depth)
    if name == "git":
        return git_deletes(peeled[1:], raws[1:], where, host)
    if name == "eval":
        return nested_bash(" ".join(peeled[1:]), where, host, depth, "eval")
    wrapped = rules.wrapped(peeled)
    if wrapped is None:
        return []
    if wrapped.dialect is rules.Dialect.BASH and wrapped.text is not None:
        return nested_bash(wrapped.text, where, host, depth, wrapped.what)
    if wrapped.dialect is rules.Dialect.POWERSHELL and wrapped.text is not None:
        if wrapped.text.strip() == "-":
            return [unnamed(wrapped.what, "the shell reads its commands from its input", where)]
        return nested_powershell(wrapped.text, where, host, depth, wrapped.what)
    if wrapped.what == "cmd /c":
        return cmd_deletes(wrapped.raw, where)
    return []


def unwrapped_further(words: list[str], raws: list[str],
                      where: Path | None) -> tuple[list[str], list[str], Path | None]:
    """words, their raw forms and the folder, past sudo, doas, exec, command -p and busybox and their
    options. sudo -D runs in a folder io-guard does not follow, and command -v runs nothing."""
    while words:
        head = program_name(words[0])
        if words[0].startswith("-"):                  # what rules.unwrapped leaves of command -p
            words, raws = words[1:], raws[1:]
        elif head in ("sudo", "doas", "exec"):
            words, raws = words[1:], raws[1:]
            while words and words[0].startswith("-"):
                valued = words[0] in SUDO_VALUED or (head == "exec" and words[0] == "-a")
                if words[0] in ("-D", "--chdir") or words[0].startswith(("-D", "--chdir=")):
                    where = None
                words, raws = (words[2:], raws[2:]) if valued else (words[1:], raws[1:])
        elif head == "command":
            if words[1:2] in (["-v"], ["-V"]):
                return [], [], where
            words, raws = words[1:], raws[1:]
        elif head == "busybox":
            words, raws = words[1:], raws[1:]
        else:
            break
    return words, raws, where


def xargs_deletes(words: list[str], where: Path | None, host: Host, depth: int) -> list[Delete]:
    """A delete with no target when the command xargs runs on its input deletes."""
    index = 0
    while index < len(words) and words[index].startswith("-"):
        index += 2 if words[index] in XARGS_VALUED else 1
    inner = words[index:]
    if not inner:
        return []
    nested = [] if program_name(inner[0]) in RM_PROGRAMS else nested_bash(rules.command_text(inner), where,
                                                                         host, depth, "xargs")
    if program_name(inner[0]) not in RM_PROGRAMS and not nested:
        return []
    return [unnamed(f"xargs {inner[0]}", "xargs reads the paths to delete from its input", where), *nested]


def rm_deletes(name: str, words: list[str], raws: list[str], where: Path | None) -> list[Delete]:
    """The targets of rm, rmdir or unlink, its options anywhere before --. rm is recursive with -r, -R or
    --recursive. An empty target deletes nothing."""
    options, targets, ended = [], [], False
    for word, raw in zip(words, raws):
        if not ended and word == "--":
            ended = True
        elif not ended and word.startswith("-") and word != "-":
            options.append(word)
        elif word:
            targets.append(raw)
    recursive = name == "rm" and any(option == "--recursive" or (not option.startswith("--")
                                                                 and re.search(r"[rR]", option))
                                     for option in options)
    how = " ".join([name, *options])
    return [Delete(how, target, recursive, Shell.BASH, where) for target in targets]


def find_deletes(words: list[str], raws: list[str], where: Path | None, host: Host,
                 depth: int) -> list[Delete]:
    """Each folder find walks, when its -exec deletes what it finds. Without a test that narrows what it
    finds, such as -name, the delete is recursive, since it reaches every name under the folder."""
    at = next((index for index, word in enumerate(words) if word in ("-exec", "-execdir", "-ok")), None)
    if at is None:
        return []
    inner = []
    for word in words[at + 1:]:
        if word in (";", "+", "\\;"):
            break
        inner.append(word)
    if not inner:
        return []
    direct = program_name(inner[0]) in RM_PROGRAMS
    nested = [] if direct else nested_bash(rules.command_text(inner), where, host, depth, "find -exec")
    if not direct and not nested:
        return []
    roots = []
    for word, raw in zip(words[1:], raws[1:]):
        if word.startswith(("-", "(", "!")):
            break
        roots.append(raw)
    tests = words[1:at]
    patterns = [tests[index + 1] for index, word in enumerate(tests[:-1]) if word in FIND_NAMING]
    reaches_git = any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns
                      for name in (".git", "./.git", ".git/x", "./.git/x", ".", "./"))
    recursive = reaches_git or not FIND_NARROWING.intersection(tests)
    how = f"find -exec {program_name(inner[0])}"
    return [*(Delete(how, root, recursive, Shell.BASH, where) for root in roots or ["."]), *nested]


def git_deletes(words: list[str], raws: list[str], where: Path | None, host: Host) -> list[Delete]:
    """The paths git clean --force or git rm deletes: its pathspecs, or the folder it runs in. git -C moves
    that folder first. git clean removes only what git does not track, never the folder it cleans or .git,
    so it is never a recursive delete of its target."""
    index = 0
    while index < len(words) and words[index].startswith("-"):
        if words[index] == "-C" and index + 1 < len(words):
            where = moved_to(shell.SimpleCommand(("cd", words[index + 1]), (), (), (0, 0)), where, host)
        index += 2 if words[index] in GIT_VALUED else 1
    if index >= len(words) or words[index] not in ("clean", "rm"):
        return []
    sub, rest, rest_raw = words[index], words[index + 1:], raws[index + 1:]
    options, specs, ended = [], [], False
    for word, raw in zip(rest, rest_raw):
        if not ended and word == "--":
            ended = True
        elif not ended and word.startswith("-"):
            options.append(word)
        else:
            specs.append(raw)
    short = "".join(option[1:] for option in options if not option.startswith("--"))
    if sub == "clean":
        if ("f" not in short and "--force" not in options) or "n" in short or "--dry-run" in options:
            return []
        return [Delete("git clean", spec, False, Shell.BASH, where) for spec in specs or ["."]]
    if "--cached" in options or "n" in short or "--dry-run" in options:
        return []
    recursive = "r" in short
    how = "git rm -r" if recursive else "git rm"
    return [Delete(how, spec, recursive, Shell.BASH, where) for spec in specs]


def powershell_deletes(command: str, cwd: Path | None, host: Host, depth: int = 0) -> list[Delete]:
    """Every delete the PowerShell command run in cwd makes, each script block read in the folder its
    command runs in. A block that changes the folder leaves it changed, so after one the folder is not
    known."""
    where = cwd
    found = [io_delete(match, where) for match in IO_DELETE.finditer(command)]
    spans = pwsh.script_block_spans(command)
    moving = [start for start, end in spans if moves_folder(command[start:end])]
    folders: list[tuple[int, Path | None]] = [(0, cwd)]
    pushed: list[Path | None] = []
    for simple in pwsh.commands(command):
        name = simple.name.lower()
        while moving and moving[0] < simple.span[0]:
            moving.pop(0)
            where = None
        folders.append((simple.span[0], where))
        if name in POP_DIRECTORY:
            where = pushed.pop() if pushed else None
        elif name in CHANGE_DIRECTORY:
            if name in PUSH_DIRECTORY:
                pushed.append(where)
            where = moved_to(simple, where, host)
        elif name in REMOVE_ITEM:
            found += remove_item(simple, where)
        elif name in INVOKE_EXPRESSION:
            found += invoke_expression(simple, where, host, depth)
        elif name in rules.SHELLS and all(word.startswith(("-", "+")) for word in simple.words[1:]) \
                and not any(word in ("--version", "--help", "-h") for word in simple.words[1:]):
            found.append(unnamed(name, "the shell reads its commands from a pipe", where, Shell.POWERSHELL))
        elif (wrapped := rules.wrapped(list(simple.words))) is not None:
            if wrapped.dialect is rules.Dialect.BASH and wrapped.text is not None:
                found += nested_bash(wrapped.text, where, host, depth, wrapped.what)
            elif wrapped.dialect is rules.Dialect.POWERSHELL and wrapped.text is not None:
                found += nested_powershell(wrapped.text, where, host, depth, wrapped.what)
            elif wrapped.what == "cmd /c":
                found += cmd_deletes(wrapped.raw, where)
    for begin, end in spans:
        block = command[begin:end]
        folder = next((held for start, held in reversed(folders) if start <= begin), cwd)
        if depth + 1 > rules.BLOCKS:
            found += unread(block, "a script block", folder)
        else:
            found += powershell_deletes(block, folder, host, depth + 1)
    return list(dict.fromkeys(found))


def moves_folder(block: str) -> bool:
    """Whether a PowerShell script block, or one inside it, runs cd, pushd, popd or Set-Location."""
    return any(simple.name.lower() in CHANGE_DIRECTORY | POP_DIRECTORY for simple in pwsh.commands(block)) \
        or any(moves_folder(inner) for inner in pwsh.script_blocks(block))


def invoke_expression(simple: shell.SimpleCommand, where: Path | None, host: Host,
                      depth: int) -> list[Delete]:
    """The deletes of the string Invoke-Expression runs, read when it is written out, else one with no
    target."""
    raws = [raw for raw in (simple.raw[1:] or simple.words[1:]) if not raw.startswith("-")]
    text = powershell_text(raws[0]) if raws else None
    if text is None:
        return [Delete("Invoke-Expression", "", True, Shell.POWERSHELL, where,
                       unnamed="Invoke-Expression runs a string io-guard cannot read")]
    return nested_powershell(text, where, host, depth, "Invoke-Expression")


def io_delete(match: re.Match, where: Path | None) -> Delete:
    """The delete of an [IO.Directory]::Delete or [IO.File]::Delete call, recursive when a directory's
    second argument is given and is not $false or 0."""
    second = (match["recursive"] or "").strip().lower()
    recursive = match["kind"].lower() == "directory" and second not in ("", "$false", "0")
    how = f"[IO.{match['kind'].capitalize()}]::Delete"
    return Delete(how, match["path"].strip(), recursive, Shell.POWERSHELL, where)


def remove_item(simple: shell.SimpleCommand, where: Path | None) -> list[Delete]:
    """The targets of Remove-Item: its -Path, -LiteralPath or first positional value, each comma-separated
    path in it. Recursive with -Recurse, given in full or by any prefix of it, unless it is :$false."""
    words, raws = list(simple.words[1:]), list(simple.raw[1:] or simple.words[1:])
    recursive, literal, given, skip = False, False, [], False
    for index, (word, raw) in enumerate(zip(words, raws)):
        if skip:
            skip = False
            continue
        flag, colon, value = word.partition(":")
        flag = flag.lower()
        if word.startswith("-") and len(flag) > 1:
            if "-recurse".startswith(flag) and len(flag) >= 2:
                recursive = value.strip().lower() not in ("$false", "0") if colon else True
            elif flag == "-whatif" and value.strip().lower() not in ("$false", "0"):
                return []
            elif flag in ("-path", "-literalpath", "-lp", "-pspath"):
                literal = literal or flag != "-path"
                if colon:
                    given.append(raw.split(":", 1)[1])
                elif index + 1 < len(words):
                    given.append(raws[index + 1])
                    skip = True
            elif flag in PS_VALUED and not colon:
                skip = True
        else:
            given.append(raw)
    how = "Remove-Item -Recurse" if recursive else "Remove-Item"
    targets = [part for text in given for part in comma_parts(text)]
    if not targets:
        return [Delete(how, "", recursive, Shell.POWERSHELL, where,
                       unnamed="Remove-Item takes the paths to delete from the pipeline")]
    return [Delete(how, target, recursive, Shell.POWERSHELL, where, literal) for target in targets]


def comma_parts(text: str) -> list[str]:
    """The paths of a PowerShell list such as a,'b c', split at each comma outside quotes."""
    parts, current, quote = [], [], ""
    for char in text:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == ",":
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def cmd_deletes(line: str, where: Path | None) -> list[Delete]:
    """The deletes of a cmd /c line: del, erase, rd and rmdir anywhere in a statement, after if exist, call
    or a parenthesis too, recursive with /s, a switch glued on as in rd/s/q. cmd reads every / as a switch.
    After a cd, chdir, pushd or popd the folder is not known."""
    line = line.strip()
    if len(line) >= 2 and line[0] == line[-1] == '"':
        line = line[1:-1]
    found = []
    for statement in re.split(r"&&|\|\||[&|]", line):
        if CMD_MOVES.match(statement):
            where = None
            continue
        if (match := CMD_DELETE_WORD.search(statement)) is None:
            continue
        name = match[1].lower()
        words = re.findall(r'"[^"]*"|/[^\s/"]+|[^\s"/()]+', statement[match.end():])
        switches = [word.lower() for word in words if word.startswith("/")]
        recursive = CMD_DELETES[name] in switches
        how = " ".join([name, *switches])
        found += [Delete(how, word, recursive, Shell.CMD, where)
                  for word in words if not word.startswith("/")]
    return found


def resolve(delete: Delete, host: Host) -> Resolved:
    """The paths a delete's target names, expanded as its shell expands it, or why it names none."""
    if delete.unnamed:
        return Resolved((), delete.unnamed)
    if "\x00" in delete.target:
        return Resolved((), "it holds a NUL character")
    match delete.shell:
        case Shell.BASH:
            return bash_paths(delete.target, delete.cwd, host, delete.wide)
        case Shell.POWERSHELL:
            return powershell_paths(delete.target, delete.cwd, host, delete.literal)
        case Shell.CMD:
            return cmd_paths(delete.target, delete.cwd, host)


Piece = tuple[str, bool]         # a character of a word, and whether it is an unquoted wildcard
QUOTE_CLOSES = {shell.DOUBLE: '"', shell.SINGLE: "'", shell.ANSI: "'"}   # each quoted state, its closing mark


def bash_pieces(raw: str) -> list[Piece] | str:
    """The characters bash makes of raw, each marked when it is an unquoted * ? or [, or why raw has no
    value before the command runs."""
    scanned, pieces, at = shell.scan(raw), [], 0
    if scanned.unterminated:
        return "its quotes do not close"
    states = scanned.states
    while at < len(raw):
        char, state = raw[at], states[at]
        if state == shell.NORMAL:
            if char in "'\"" or (char == "$" and raw[at + 1:at + 2] in ("'", '"')):
                at += 1
                continue
            if char == "\\":
                pieces.append((raw[at + 1:at + 2], False))
                at += 2
                continue
            if char in "$`":
                return LATER
            if char == "{" and BRACE_LIST.match(raw, at):
                return "it holds a brace list, which bash expands into several words"
            pieces.append((char, char in "*?["))
        elif (closing := QUOTE_CLOSES.get(state)) is not None:
            if char == closing:
                at += 1
                continue
            if state == shell.DOUBLE and char == "\\" and raw[at + 1:at + 2] in shell.ESCAPED_IN_DOUBLE:
                pieces.append((raw[at + 1], False))
                at += 2
                continue
            if state == shell.DOUBLE and char in "$`":
                return LATER
            if state == shell.ANSI and char == "\\":
                return "it holds an escape inside $'...'"
            pieces.append((char, False))
        else:
            return "it holds a part bash reads as code"
        at += 1
    return pieces


def bash_paths(raw: str, cwd: Path | None, host: Host, wide: bool = False) -> Resolved:
    """The paths a Bash word names: its tilde, its wildcards expanded as bash expands them, then each word
    read as a path the way Git Bash passes it on. An empty word names nothing."""
    pieces = bash_pieces(raw)
    if isinstance(pieces, str):
        return Resolved((), pieces)
    text = "".join(char for char, _ in pieces)
    if raw.startswith("~"):                  # a ~ bash expands is the first character, outside quotes
        head, _, _ = text.partition("/")
        if head != "~":
            return Resolved((), "it names another user's home folder")
        home = host.env.get("HOME") or host.env.get("USERPROFILE")
        if not home:
            return Resolved((), "no HOME names the home folder")
        pieces = [(char, False) for char in home.replace("\\", "/")] + pieces[1:]
        text = home.replace("\\", "/") + text[1:]
    if not text:
        return Resolved(())
    words, globbed = [text], any(live for _, live in pieces)
    if globbed:
        expanded = bash_glob(pieces, cwd, host, wide)
        if isinstance(expanded, str):
            return Resolved((), expanded)
        words = expanded or words
    found = []
    for word in words:
        path = git_bash_path(word, cwd, host)
        if isinstance(path, str):
            return Resolved((), path)
        found.append(path)
    return Resolved(tuple(found), globbed=globbed)


def bash_glob(pieces: list[Piece], cwd: Path | None, host: Host, wide: bool) -> list[str] | str:
    """The words bash makes of a word with a wildcard: each match, shown as Git Bash shows its names, or no
    word when nothing matches and bash passes the word as written. wide matches dot names and any case."""
    base = git_bash_base("".join(char for char, _ in pieces), cwd, host)
    if isinstance(base, str):
        return base
    shown, real, consumed = base
    parts = split_pieces(pieces[consumed:])
    matches: list[tuple[str, Path]] = [(shown, real)]
    examined = 0
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        if not part:
            if last:
                matches = [(word + "/", path) for word, path in matches if host.fs.is_dir(path)]
            continue
        name = "".join(char for char, _ in part)
        if not any(live for _, live in part):
            matches = [(join(word, name), path / to_disk_name(name, host)) for word, path in matches]
            continue
        pattern = "".join(char if live else glob_escape(char) for char, live in part).replace("[^", "[!")
        grown = []
        for word, folder in matches:
            listed = list_folder(folder, host)
            if isinstance(listed, str):
                return listed
            examined += len(listed)
            if examined > GLOB_LIMIT:
                return TOO_MANY
            for entry in listed:
                shown_name = from_disk_name(entry.name, host)
                if shown_name.startswith(".") and not name.startswith(".") and not wide:
                    continue
                hit = (fnmatch.fnmatchcase(shown_name.casefold(), pattern.casefold()) if wide
                       else fnmatch.fnmatchcase(shown_name, pattern))
                if hit and (last or host.fs.is_dir(entry)):
                    grown.append((join(word, shown_name), entry))
        matches = grown
    return [word for word, _ in matches] if matches and parts else []


def git_bash_base(text: str, cwd: Path | None, host: Host) -> tuple[str, Path, int] | str:
    """Where a Bash word's first name starts: the word as shown so far, the folder on disk, and how many of
    the word's characters that took. A relative word starts at cwd."""
    windows = host.platform.windows
    if windows and (drive := re.match(r"^/([A-Za-z])(/|$)", text)):
        return f"/{drive[1]}/", Path(f"{drive[1].upper()}:/"), len(drive[0])
    if windows and (drive := re.match(r"^([A-Za-z]):/?", text)):
        return drive[0], Path(f"{drive[1].upper()}:/"), len(drive[0])
    if windows and re.match(r"^/tmp(/|$)", text):
        temps = paths.temp_folders(host.platform, host.env)
        return ("/tmp/", temps[0], 5) if temps else "no TEMP names the temp folder"
    if text.startswith("/"):
        if windows:
            return "it names a Git Bash folder, which io-guard cannot place on disk"
        return "/", Path("/"), 1
    if cwd is None:
        return RELATIVE_LOST
    return "", cwd, 0


def git_bash_path(word: str, cwd: Path | None, host: Host) -> Path | str:
    """The path a program Git Bash starts reads in word, or why it has none."""
    if not host.platform.windows:
        if not word.startswith("/") and cwd is None:
            return RELATIVE_LOST
        return paths.normalise(word, cwd or Path("/"), host.platform)
    if drive := re.match(r"^/([A-Za-z])(?=/|$)", word):
        word = f"{drive[1].upper()}:{word[2:] or '/'}"
    elif re.match(r"^/tmp(/|$)", word):
        temps = paths.temp_folders(host.platform, host.env)
        if not temps:
            return "no TEMP names the temp folder"
        word = temps[0].as_posix() + word[4:]
    elif word.startswith("/"):
        return "it names a Git Bash folder, which io-guard cannot place on disk"
    drive = re.match(r"^[A-Za-z]:", word)
    head, rest = (word[:2].upper() + "/", word[2:].lstrip("/\\")) if drive else ("", word)
    if not drive and cwd is None:
        return RELATIVE_LOST
    rest = "/".join(to_disk_name(name, host) for name in re.split(r"[/\\]", rest))
    return paths.normalise(head + rest, cwd or Path(head), host.platform)


def powershell_paths(raw: str, cwd: Path | None, host: Host, literal: bool) -> Resolved:
    """The paths a PowerShell word names, its wildcards expanded without case unless it is literal."""
    text = powershell_text(raw)
    if text is None:
        return Resolved((), "it holds a variable, an expression or a splatted table, which has a value only "
                            "when the command runs")
    if NOT_FILES.match(text):
        return Resolved(())
    if PROVIDER.search(text):
        return Resolved((), "it names a PowerShell provider, not a folder")
    return expanded_paths(text, cwd, host, globbing=not literal and bool(re.search(r"[*?\[]", text)),
                          whole=True)


def powershell_text(raw: str) -> str | None:
    """The text a PowerShell word passes, or None when it holds a variable, an expression or a splat."""
    if len(raw) >= 2 and raw[0] == raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if len(raw) >= 2 and raw[0] == raw[-1] == '"':
        inner = raw[1:-1]
        return None if "$" in inner else re.sub(r"`(.)", r"\1", inner)
    if "$" in raw or raw.startswith(("(", "@")):
        return None
    return re.sub(r"`(.)", r"\1", raw)


def cmd_paths(raw: str, cwd: Path | None, host: Host) -> Resolved:
    """The paths a cmd word names, * and ? matched without case in its last name."""
    text = raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] == '"' else raw
    if "%" in text or "!" in text:
        return Resolved((), "it holds a variable, which has a value only when the command runs")
    return expanded_paths(text.replace("^", ""), cwd, host, globbing=bool(re.search(r"[*?]", text)),
                          whole=False)


def expanded_paths(text: str, cwd: Path | None, host: Host, globbing: bool, whole: bool) -> Resolved:
    """The paths a Windows-style path names, with ~ for the home folder, and its wildcards matched without
    case in every name when whole, or in the last name only, as cmd does. No match leaves the path as
    written."""
    if text.startswith("~"):
        home = host.env.get("USERPROFILE") or host.env.get("HOME")
        if text[1:2] not in ("", "/", "\\") or not home:
            return Resolved((), "it names a home folder io-guard cannot place")
        text = home + text[1:]
    if not text:
        return Resolved(())
    if cwd is None and not re.match(r"^(?:[A-Za-z]:)?[\\/]", text):
        return Resolved((), RELATIVE_LOST)
    path = paths.normalise(text, cwd or Path("/"), host.platform)
    if not globbing:
        return Resolved((path,))
    names = path.parts
    matches = [Path(names[0])]
    examined = 0
    for index, name in enumerate(names[1:], 1):
        live = bool(re.search(r"[*?\[]", name)) and (whole or index == len(names) - 1)
        if not live:
            matches = [match / name for match in matches]
            continue
        grown = []
        for folder in matches:
            listed = list_folder(folder, host)
            if isinstance(listed, str):
                return Resolved((), listed)
            examined += len(listed)
            if examined > GLOB_LIMIT:
                return Resolved((), TOO_MANY)
            grown += [entry for entry in listed if fnmatch.fnmatch(entry.name.casefold(), name.casefold())]
        matches = grown
    return Resolved(tuple(matches) if matches else (path,), globbed=True)


def list_folder(folder: Path, host: Host) -> tuple[Path, ...] | str:
    """The entries of folder, () when it is missing, or why it cannot be listed."""
    try:
        return host.fs.entries(folder)
    except (FileNotFoundError, NotADirectoryError):
        return ()
    except OSError as error:
        return f"io-guard cannot list {folder.as_posix()} to expand its wildcard: {error.strerror or error}"


def split_pieces(pieces: list[Piece]) -> list[list[Piece]]:
    """pieces split at each /, the names of a path, the last empty when the word ends with /."""
    parts: list[list[Piece]] = [[]]
    for piece in pieces:
        if piece[0] == "/":
            parts.append([])
        else:
            parts[-1].append(piece)
    return parts


def join(word: str, name: str) -> str:
    return name if not word else word + name if word.endswith("/") else f"{word}/{name}"


def glob_escape(char: str) -> str:
    return f"[{char}]" if char in "*?[" else char


def to_disk_name(name: str, host: Host) -> str:
    """name as Windows stores a name Git Bash shows: each : * ? \" < > | as U+F000 + its code."""
    if not host.platform.windows:
        return name
    return "".join(chr(PRIVATE + ord(char)) if char in MSYS_MAPPED else char for char in name)


def from_disk_name(name: str, host: Host) -> str:
    """name as Git Bash shows a name Windows stores: each U+F000 + c below U+F080 as the character c."""
    if not host.platform.windows:
        return name
    return "".join(chr(ord(char) - PRIVATE) if PRIVATE < ord(char) < PRIVATE + 0x80 else char
                   for char in name)
