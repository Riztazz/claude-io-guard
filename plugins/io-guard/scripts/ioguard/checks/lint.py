"""Catch the quoting, escaping and dialect mistakes a shell command shows before it runs.

Each rule reads the command as its shell will. In Bash, a backtick inside double quotes runs its text as a
command (SHW-5). A double-quoted Windows path that ends in a backslash escapes its own closing quote (SHW-7),
and the check rewrites the path to forward slashes under the user's rewrite mode (D12). A Python body that
does not compile is refused before any part of the command runs, and one that compiles with a warning, such
as an invalid escape, runs with that warning (SHW-6). PowerShell syntax in the Bash tool and bash syntax in
the PowerShell tool are refused (SHL-1), and so are the PowerShell calls that always fail (SHL-4, SHL-5). A
build or test piped into a filter gets a warning that the exit code shown is the filter's (OUT-1). The check
runs after transport.body, so a body moved into a file is compiled from that file, byte-exact.
"""
import re
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import pwsh, python_source, shell
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Fix, Layer, Result, Severity

POWERSHELLS = frozenset({"powershell", "pwsh"})
CMDLET = re.compile(r"^(?:get|set|new|remove|select|where|foreach|write|test|start|stop|invoke|out"
                    r"|format|measure|sort|copy|move|rename|import|add|clear|convertto|convertfrom|join"
                    r"|split|resolve|wait)-[a-z]+$")
BASH_EXPANDS = re.compile(r"\$(?:\{?env:|PSItem\b|LASTEXITCODE\b|PSScriptRoot\b|PSVersionTable\b"
                          r"|ErrorActionPreference\b)", re.I)
POWERSHELL_ONLY = re.compile(r"\$(?:_(?!\w)|\{?env:|PSItem\b|true\b|false\b|null\b|LASTEXITCODE\b)", re.I)
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
    cmdlet = next((simple for simple in simples if CMDLET.match(simple.name)), None)
    if cmdlet is not None:
        findings.add(Code.DIALECT_MISMATCH, f"{cmdlet.words[0]} is a PowerShell cmdlet, and bash has no such "
                     f"command.", TO_POWERSHELL, offset=cmdlet.span[0])
    here = next((match for match in HERE_STRING.finditer(command)
                 if found.states[match.start()] == shell.NORMAL), None)
    if here is not None:
        findings.add(Code.DIALECT_MISMATCH,
                     "This command holds a PowerShell here-string, which bash reads as ordinary quotes.",
                     "Send the command to the PowerShell tool, or use a bash heredoc.", offset=here.start())


def python_bodies(command: str, found: shell.Scan, simples: tuple[shell.SimpleCommand, ...],
                  ctx: Context) -> list[str]:
    """Each Python program the command runs whose text is known as Python will read it: a heredoc or
    python -c body that bash passes unchanged and the Bash tool does not halve, or a body moved to a file."""
    halving = ctx.probe.halving is True

    def halved(span: tuple[int, int]) -> bool:
        return halving and any(span[0] <= at < span[1] for at in found.hazards)

    bodies = []
    for heredoc in found.heredocs:
        owner = next((simple for simple in simples
                      if simple.span[0] <= heredoc.operator[0] < simple.span[1]), None)
        unchanged = heredoc.quoted or not re.search(r"[$`\\]", heredoc.body)
        if owner is not None and shell.python_reads_stdin(owner) and heredoc.terminated and unchanged \
                and not halved(heredoc.span):
            bodies.append(heredoc.body)
    bodies += [body.body for body in found.bodies if not body.expands and not halved(body.argument)]
    for simple in simples:
        if not shell.PYTHON.match(simple.name):
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


def build_label(simple: shell.SimpleCommand, builds: list[str]) -> str | None:
    """The build or test command simple runs, as its entry in builds names it, or None."""
    for entry in builds:
        words = entry.lower().split()
        head = re.split(r"[\\/]", words[0])[-1].removesuffix(".exe")
        named = shell.PYTHON.match(simple.name) if head == "python" else simple.name == head
        if named and [word.lower() for word in simple.words[1:len(words)]] == words[1:]:
            return " ".join(simple.words[:len(words)])
    return None


def hidden_exit(command: str, simples: tuple[shell.SimpleCommand, ...], builds: list[str],
                findings: Findings) -> None:
    if re.search(r"pipefail|PIPESTATUS", command):
        return
    for index, simple in enumerate(simples[:-1]):
        label = build_label(simple, builds)
        if label and shell.piped(command, simple):
            into = simples[index + 1].name
            findings.add(Code.PIPE_HIDES_EXIT, f"This command pipes {label} into {into}, so the exit code "
                         f"shown is {into}'s, not {label}'s.", "Read the output for the result, not the exit "
                         "code.", command=label)
            return


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


class Lint(Check):
    meta = CheckMeta(
        id="shell.lint", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.REFUSED, cost=Cost.MEDIUM, reads=frozenset({"command"}),
        writes=frozenset({"command"}), after=frozenset({"transport.body"}),
        config={"build_commands": ConfigKey(list, BUILD_COMMANDS,
                                            "Commands whose exit code a pipe into a filter hides, each as "
                                            "its first words, such as make or npm test.")},
        codes=frozenset({Code.BACKTICK_IN_DOUBLE_QUOTES, Code.TRAILING_BACKSLASH_QUOTE,
                         Code.DIALECT_MISMATCH, Code.POWERSHELL_TRAP, Code.PIPE_HIDES_EXIT,
                         Code.INLINE_SCRIPT_INVALID}),
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
        hidden_exit(command, simples, self.options["build_commands"], findings)
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
