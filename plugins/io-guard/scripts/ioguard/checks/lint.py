"""Catch the quoting, escaping and dialect mistakes a shell command shows before it runs.

Each rule reads the command as its shell will. In Bash, a backtick inside double quotes runs its text as a
command (SHW-5). A double-quoted Windows path that ends in a backslash escapes its own closing quote (SHW-7),
and the check rewrites the path to forward slashes under the user's rewrite mode (D12). A Python body that
does not compile is refused before any part of the command runs, and one that compiles with a warning, such
as an invalid escape, runs with that warning (SHW-6). PowerShell syntax in the Bash tool and bash syntax in
the PowerShell tool are refused (SHL-1), and so are the PowerShell calls that always fail (SHL-4, SHL-5). The
first build or test a session pipes into a filter gets a warning that the exit code shown is the filter's
(OUT-1). Later ones get none here, because shell.results names what a pipe hid after each run. A command
that stops processes by a shared runtime's name, such as python, or by a command-line match gets a warning,
since it stops other sessions' servers too. The check runs after transport.body, so a body moved into a file
is compiled from that file, byte-exact.
"""
import re
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import kills, portable, pwsh, python_source, shell
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.program import program_name
from ioguard.lib.results import Code, Fix, Layer, Result, Severity

POWERSHELLS = frozenset({"powershell", "pwsh"})
# A cmdlet as PowerShell writes it, Verb-Noun with capitals, or one of the common ones in any case. A lower
# case verb-noun is also how programs such as wait-on or start-server are named.
CMDLET = re.compile(r"^(?:Get|Set|New|Remove|Select|Where|ForEach|Write|Test|Start|Stop|Invoke|Out|Format"
                    r"|Measure|Sort|Copy|Move|Rename|Import|Add|Clear|ConvertTo|ConvertFrom|Join|Split"
                    r"|Resolve|Wait)-[A-Z][A-Za-z]+$")
COMMON_CMDLETS = frozenset({
    "get-childitem", "get-content", "set-content", "add-content", "clear-content", "select-string",
    "select-object", "where-object", "foreach-object", "sort-object", "measure-object", "remove-item",
    "copy-item", "move-item", "new-item", "rename-item", "get-item", "test-path", "resolve-path", "join-path",
    "split-path", "write-host", "write-output", "get-process", "stop-process", "start-process", "get-date",
    "start-sleep", "set-location", "get-location", "invoke-webrequest", "invoke-restmethod", "out-file",
    "convertto-json", "convertfrom-json", "format-table", "format-list", "get-command", "import-module"})
BASH_EXPANDS = re.compile(r"\$(?:\{?env:(?=[A-Za-z_])|PSItem\b|LASTEXITCODE\b|PSScriptRoot\b|PSVersionTable\b"
                          r"|ErrorActionPreference\b)", re.I)
POWERSHELL_ONLY = re.compile(r"\$(?:_(?!\w)|\{?env:(?=[A-Za-z_])|PSItem\b|true\b|false\b|null\b"
                             r"|LASTEXITCODE\b)", re.I)
HERE_STRING = re.compile(r"@['\"][ \t]*\n")
READ_ONLY = ("pid|home|host|pshome|shellid|true|false|executioncontext|psversiontable|error|psculture"
             "|psuiculture|psedition")
ASSIGNED = re.compile(rf"(?:^|[\s{{(;|])\$({READ_ONLY})\s*=(?!=)", re.I)
LOOPED = re.compile(rf"\(\s*\$({READ_ONLY})\s+in\b", re.I)
BUILD_COMMANDS = ["make", "cmake --build", "ninja", "msbuild", "dotnet build", "dotnet test", "cargo build",
                  "cargo test", "go build", "go test", "npm test", "npm run", "pnpm test", "yarn test",
                  "pytest", "python -m pytest", "python -m unittest", "tox", "gradle", "gradlew", "mvn",
                  "tsc", "ctest"]
TO_POWERSHELL = "Send the command to the PowerShell tool, or write it for bash."


class Findings:
    """The results one command gets, in the order the rules find them."""

    def __init__(self, event: Event, ctx: Context) -> None:
        self.event, self.ctx = event, ctx
        self.results: list[Result] = []

    def add(self, code: Code, message: str, fix: str, severity: Severity | None = None, **evidence) -> None:
        fields = {} if severity is None else {"severity": severity}
        self.results.append(Result.of(code, message, self.event.tool_name, self.ctx.platform.os,
                                      evidence=evidence, fix=Fix(self.event.tool_name, {}, fix), **fields))


def shown(command: str, at: int) -> str:
    return command[max(0, at - 30):at + 30].replace("\n", " ").strip()


def expanded(command: str, states: bytes, at: int) -> bool:
    """Whether bash expands the $ at at: unquoted or in double quotes, and not escaped."""
    return states[at] in (shell.NORMAL, shell.DOUBLE) and command[at - 1:at] != "\\"


def bash_dialect(command: str, found: shell.Scan, simples: tuple[shell.SimpleCommand, ...],
                 findings: Findings) -> None:
    """PowerShell syntax in a Bash command: the call operator, a variable bash expands, a cmdlet run as a
    program, and a here-string."""
    for at in shell.call_operators(command, found.states)[:1]:
        findings.add(Code.DIALECT_MISMATCH,
                     f"This command starts a command with &, PowerShell's call operator, which bash reads "
                     f"as a syntax error: {shown(command, at)}",
                     "Run the program by its path with no & before it, or send the command to the PowerShell "
                     "tool.", offset=at)
    inside = [simple.span for simple in simples if simple.name in POWERSHELLS]
    for match in POWERSHELL_ONLY.finditer(command):
        at = match.start()
        if expanded(command, found.states, at) and any(start <= at < end for start, end in inside):
            findings.add(Code.DIALECT_MISMATCH, f"Bash expands {match[0]} inside the text it hands to "
                         f"PowerShell, so PowerShell never sees it: {shown(command, at)}", "Put the -Command "
                         "text in single quotes, or send it to the PowerShell tool.", offset=at)
            break
    for match in BASH_EXPANDS.finditer(command):
        at = match.start()
        if expanded(command, found.states, at) and not any(start <= at < end for start, end in inside):
            findings.add(Code.DIALECT_MISMATCH, f"This command uses {match[0]}, PowerShell syntax that bash "
                         f"expands to something else: {shown(command, at)}", TO_POWERSHELL, offset=at)
            break
    cmdlet = next((simple for simple in simples if simple.words and (
        CMDLET.match(program_name(simple.words[0], (), fold=False)) or simple.name in COMMON_CMDLETS)), None)
    if cmdlet is not None:
        findings.add(Code.DIALECT_MISMATCH, f"{cmdlet.words[0]} is a PowerShell cmdlet, and bash has no such "
                     f"command.", TO_POWERSHELL, offset=cmdlet.span[0])
    here = next((match for match in HERE_STRING.finditer(command)
                 if found.states[match.start()] == shell.NORMAL), None)
    if here is not None:
        findings.add(Code.DIALECT_MISMATCH,
                     "This command holds a PowerShell here-string, which bash reads as ordinary quotes.",
                     "Send the command to the PowerShell tool, or use a bash heredoc.", offset=here.start())


def unportable(command: str, found: shell.Scan, simples: tuple[shell.SimpleCommand, ...], ctx: Context,
               findings: Findings) -> None:
    """bash 4 syntax when the session probe measured an older bash, and GNU-only options on macOS, whose
    tools are BSD's. Each is a warning, because the command may still do what was meant."""
    old = portable.major(ctx.probe.bash.version if ctx.probe.bash else None)
    named = f"bash {ctx.probe.bash.version}" if ctx.probe.bash else "bash"
    lacks = []
    if old is not None and old < 4:
        lacks += [(each, f"{named} lacks it") for each in portable.bash4(command, found.states, simples)]
    if ctx.platform.macos:
        lacks += [(each, "macOS's BSD tools read it another way") for each in portable.gnu_only(simples)]
    for each, why in lacks[:3]:
        findings.add(Code.NOT_PORTABLE, f"This command uses {each.what}, and {why}: "
                                        f"{shown(command, each.offset)}", each.fix, severity=Severity.WARNING,
                     offset=each.offset)


def python_bodies(command: str, found: shell.Scan, simples: tuple[shell.SimpleCommand, ...],
                  ctx: Context) -> list[str]:
    """Each Python program the command runs whose text is known as Python will read it: a heredoc or
    python -c body that bash passes unchanged and the Bash tool does not halve, or a body moved to a file."""
    halving = ctx.probe.halving is True

    def halved(span: tuple[int, int]) -> bool:
        return halving and any(span[0] <= at < span[1] for at in found.hazards)

    def owner(offset: int) -> shell.SimpleCommand | None:
        return next((simple for simple in simples if simple.span[0] <= offset < simple.span[1]), None)

    bodies = []
    for heredoc in found.heredocs:
        runs = owner(heredoc.operator[0])
        unchanged = heredoc.quoted or not re.search(r"[$`\\]", heredoc.body)
        if runs is not None and shell.python_reads_stdin(runs) and python3(runs) and heredoc.terminated \
                and unchanged and not halved(heredoc.span):
            bodies.append(heredoc.body)
    bodies += [body.body for body in found.bodies if not body.expands and not halved(body.argument)
               and ((runs := owner(body.argument[0])) is None or python3(runs))]
    for simple in simples:
        if not shell.PYTHON.match(simple.name) or not python3(simple):
            continue
        named = shell.body_files(" ".join(simple.words))
        if shell.python_reads_stdin(simple):
            named += shell.body_files(" ".join(simple.inputs))
        for path in named:
            try:
                bodies.append(ctx.fs.read_bytes(Path(path)).decode("utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return bodies


def python3(simple: shell.SimpleCommand) -> bool:
    """Whether the command runs a Python 3, whose compiler io-guard's own is: not python2, and not py -2."""
    if simple.name.startswith("python2"):
        return False
    return not (simple.name == "py" and any(re.match(r"^-2(?:\.\d+)?$", word) for word in simple.words[1:2]))


def python(bodies: list[str], findings: Findings) -> None:
    for body in bodies:
        report = python_source.compile_report(body)
        if report is None:
            continue
        if report.error is not None:
            error = report.error
            where = f", at line {error.line}: {error.text}" if error.line else ""
            findings.add(Code.INLINE_SCRIPT_INVALID,
                         f"The Python program in this command does not compile: {error.message}{where}",
                         "Fix that line, then run the command again.", line=error.line)
            return
        if report.warnings:
            warning = report.warnings[0]
            findings.add(Code.INLINE_SCRIPT_INVALID, f"Python warns about line {warning.line} of the program "
                         f"in this command: {warning.message}", "Change that line so it says what it means, "
                         "or the program may do something else.", Severity.WARNING, line=warning.line)
            return


def hidden_exit(command: str, simples: tuple[shell.SimpleCommand, ...],
                builds: list[str]) -> tuple[str, str] | None:
    """The first build piped into another command, and that command's name, unless pipefail or PIPESTATUS
    keeps the build's exit code."""
    if re.search(r"pipefail|PIPESTATUS", command):
        return None
    for index, simple in enumerate(simples[:-1]):
        label = shell.matching(simple, builds)
        if label and shell.piped(command, simple):
            return label, simples[index + 1].name
    return None


def broad_stop(command: str, code: str, findings: Findings) -> None:
    """A stop of processes other sessions run too, by a shared runtime's name or by a command-line match. A
    warning only, since stopping every copy of a program is sometimes what the user wants."""
    stop = kills.broad_stop(command, code)
    if stop is not None:
        findings.add(Code.STOPS_BY_MATCH,
                     f"This command stops {stop}, whatever started it, so it can stop other Claude Code "
                     f"sessions' servers too.",
                     "Stop the one process by its id: take it from the port the process listens on, or from "
                     "what its start printed.", Severity.WARNING, stop=stop)


def powershell(command: str, findings: Findings) -> None:
    """Bash syntax in a PowerShell command, and the PowerShell calls that always fail. On macOS /dev/null,
    tail and head exist, so only Windows gets those two rules."""
    windows = findings.ctx.platform.windows
    for simple in pwsh.commands(command):
        if simple.name == "export":
            findings.add(Code.DIALECT_MISMATCH, "export is a bash command, and PowerShell has none.",
                         "Set the variable with $env:NAME = 'value'.")
        elif any(word.startswith("<<") for word in simple.words):
            findings.add(Code.DIALECT_MISMATCH, "This command holds a bash heredoc, and PowerShell cannot "
                         "parse <<.", "Pipe a here-string instead: @'...'@ | command.")
        elif simple.name in ("tail", "head") and windows:
            findings.add(Code.DIALECT_MISMATCH,
                         f"{simple.words[0]} is not a PowerShell command, and runs only when a program by "
                         f"that name is on the PATH.", "Use Select-Object -Last N or -First N.",
                         Severity.WARNING)
        elif simple.name in ("select-string", "sls") and "-recurse" in map(str.lower, simple.words):
            findings.add(Code.POWERSHELL_TRAP,
                         "Select-String has no -Recurse parameter, so PowerShell refuses this command.",
                         "Pipe the files in: Get-ChildItem -Recurse -File | Select-String -Pattern ...")
        if windows and any(redirect.target == "/dev/null" for redirect in simple.redirects):
            findings.add(Code.DIALECT_MISMATCH,
                         "PowerShell reads /dev/null as the path C:/dev/null, which does not exist.",
                         "Redirect to $null instead.")
    code = pwsh.blanked(command)
    taken = ASSIGNED.search(code) or LOOPED.search(code)
    if taken is not None:
        findings.add(Code.POWERSHELL_TRAP, f"PowerShell refuses to assign ${taken[1]}, a read-only automatic "
                     f"variable.", "Give the variable another name.")
    broad_stop(command, code, findings)


class Lint(Check):
    meta = CheckMeta(
        id="shell.lint", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.REFUSED, cost=Cost.MEDIUM, reads=frozenset({"command"}),
        writes=frozenset({"command"}), after=frozenset({"transport.body"}),
        config={"build_commands": ConfigKey(list, BUILD_COMMANDS,
                                            "Commands whose exit code a pipe into a filter hides, each as "
                                            "its first words, such as make or npm test. A project's list "
                                            "replaces it.")},
        codes=frozenset({Code.COMMAND_TOO_DEEP, Code.BACKTICK_IN_DOUBLE_QUOTES, Code.TRAILING_BACKSLASH_QUOTE,
                         Code.DIALECT_MISMATCH, Code.POWERSHELL_TRAP, Code.PIPE_HIDES_EXIT,
                         Code.INLINE_SCRIPT_INVALID, Code.NOT_PORTABLE, Code.STOPS_BY_MATCH}),
        description="Refuses a shell command whose quoting, escaping or dialect would change what runs, and "
                    "fixes a Windows path whose last backslash escapes its quote.")

    def run(self, event: Event, ctx: Context) -> Decision:
        command, findings, rewrite = event.command or "", Findings(event, ctx), None
        if event.tool is Tool.POWERSHELL:
            powershell(command, findings)
        else:
            rewrite = self.bash(command, ctx, findings)
        refusals = [result for result in findings.results if result.severity is Severity.REFUSED]
        warnings = [result for result in findings.results if result.severity is Severity.WARNING]
        if refusals:
            return Decision(self.meta.id, Verdict.DENY, results=(refusals[0], *warnings))
        if rewrite is not None or warnings:
            return Decision(self.meta.id, Verdict.ALLOW, results=tuple(warnings), rewrite=rewrite)
        return Decision.observe(self.meta.id)

    def bash(self, command: str, ctx: Context, findings: Findings) -> Rewrite | None:
        found = shell.scan(command)
        if found.too_deep:
            findings.add(Code.COMMAND_TOO_DEEP, f"This command nests $() more than {shell.MAX_NESTING} deep, "
                         f"past what io-guard reads, so its checks cannot see all of it.",
                         "Put the inner commands in a script file with the Write tool, then run the file.")
        simples = shell.commands(command, found)
        bash_dialect(command, found, simples, findings)
        if found.backticks:
            at = found.backticks[0]
            findings.add(Code.BACKTICK_IN_DOUBLE_QUOTES,
                         f"Bash runs the text between backticks inside double quotes as a command, here: "
                         f"{shown(command, at)}",
                         "Put that text in single quotes, or escape each backtick with a backslash.",
                         offset=at)
        python(python_bodies(command, found, simples, ctx), findings)
        piped = hidden_exit(command, simples, self.options["build_commands"])
        if piped is not None and ctx.session.first_time("pipe-hides-exit"):
            label, into = piped
            findings.add(Code.PIPE_HIDES_EXIT, f"This command pipes {label} into {into}, so the exit code "
                         f"shown is {into}'s, not {label}'s.", "Read the output for the result, not the exit "
                         "code.", command=label)
        unportable(command, found, simples, ctx, findings)
        broad_stop(command, shell.blanked(command, found), findings)
        return self.trailing_backslashes(command, found)

    def trailing_backslashes(self, command: str, found: shell.Scan) -> Rewrite | None:
        """The rewrite that turns each double-quoted Windows path escaping its quote to forward slashes, when
        that is what leaves bash a command it can read to the end."""
        spans = shell.trailing_backslash_paths(command) if found.unterminated else ()
        if not spans:
            return None
        rewritten = shell.forward_slashed(command, spans)
        if shell.scan(rewritten).unterminated:
            return None
        paths = ", ".join(rewritten[start:end] for start, end in spans)
        note = (f"io-guard wrote {paths} with forward slashes, because a backslash before a closing double "
                f"quote escapes the quote in bash.")
        return Rewrite(self.meta.id, frozenset({"command"}), lambda given: {**given, "command": rewritten},
                       note, Code.TRAILING_BACKSLASH_QUOTE)
