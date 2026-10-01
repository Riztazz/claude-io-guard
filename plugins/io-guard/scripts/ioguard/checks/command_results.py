"""Say what a shell command's result means: which exit code is an answer rather than a failure, which lines
report errors, what a long saved output holds, and when the text came through the wrong code page.

A failed Bash call's output arrives in the event's error, after its "Exit code N" line, and a call that ran
brings stdout and stderr in tool_response (context.md, "Hooks and MCP", row 32). Exit code 1 from grep, diff
or test is an answer (OUT-3), and when it stopped an && chain the model learns that the rest never ran. Error
lines count only when a pattern matches from the line's start, and never in the output of a command that
reads a file or a log, because that output quotes errors rather than raising them (OUT-7). A pipe that ends
in a filter hides the failure before it (OUT-1). An output Claude Code saved to a file is replaced by its
first and last lines and its error lines, so the model need not read the file again (OUT-10). A build that
failed marks the programs a later run uses as stale (VFY-7). A well-formed Bash command over 5 KB that the
Bash tool's own bash, bash -c, read as ending inside a quote was cut by this machine's Bash tool, so the
session's transport budget drops below its length. On macOS, where no cut is known, it drops at the second.
"""
import logging
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from functools import cached_property
from pathlib import Path
from typing import Any

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import output, pwsh, shell
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.folders import claude_folder
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.results import Code, Fix, Layer, Result, Severity

log = logging.getLogger("ioguard.checks.command_results")

ERROR_PATTERNS = {
    "compiler": [r"^[ \t]*(?:\d+>)?(?:[^\s:(][^\n(]*\(\d+(?:,\d+)*\)[ \t]*:[ \t]*|[A-Za-z]+[ \t]+:[ \t]*)?"
                 r"(?:fatal[ \t]+)?error[ \t]+[A-Z]{1,8}\d{2,5}[ \t]*:",
                 r"^(?:[A-Za-z]:)?[^\s:][^:\n]*:\d+:(?:\d+:)?[ \t]+(?:fatal[ \t]+)?error:",
                 r"^error\[E\d{4}\]:"],
    "exception": [r"^(?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:Error|Exception)(?::|\r?$)"],
    "test": [r"^(?:FAILED|ERROR) \S+::", r"^(?:FAIL|ERROR): \w+ \(", r"^--- FAIL: ",
             r"^test \S+ \.\.\. FAILED", r"^[ \t]*Failed \S+ \[\d"],
    "build": [r"^(?:g?make|mingw32-make)(?:\[\d+\])?: \*\*\* ", r"^Build FAILED\.", r"^npm ERR! ",
              r"^CMake Error\b"],
    "tool": [r"^(?:error|fatal|ERROR|FATAL): "],
}
FAILED_BUILD = frozenset({"compiler", "build"})
BENIGN_EXITS = {
    **{name: {"1": "no line matches"} for name in ("grep", "egrep", "fgrep", "rg", "git grep", "findstr")},
    **{name: {"1": "the inputs differ"} for name in ("diff", "cmp", "fc", "git diff --no-index",
                                                     "git diff --exit-code")},
    **{name: {"1": "the test is false"} for name in ("test", "[", "[[")},
    **{name: {"5": "it collects no test"} for name in ("pytest", "python -m pytest")},
    "python -m unittest": {"5": "it finds no test to run"},
}
READERS = ["ls", "dir", "grep", "egrep", "fgrep", "rg", "ag", "ack", "findstr", "cat", "head", "tail", "less",
           "more", "sed", "awk", "sort", "uniq", "wc", "cut", "tr", "jq", "git grep", "git log", "git show",
           "git diff", "select-string", "sls", "get-content", "gc", "type"]
QUIET = frozenset({"echo", "printf", "true", ":", "cd", "pushd", "popd", "export", "unset", "set", "sleep"})
RUNS = ["ctest", "dotnet test --no-build", "dotnet run --no-build"]
SHELL_ERROR = re.compile(r"^(?:/usr/bin/)?bash(?:\.exe)?: ", re.M)
# The Bash tool's own bash reports its -c text, while a script names its file and eval names eval.
CUT = re.compile(r"^(?:\S*/)?bash(?:\.exe)?: -c: line \d+: unexpected EOF while looking for matching", re.M)
READ_AS_UTF8 = ("Read the input as UTF-8, such as open(path, encoding=\"utf-8\") in Python or Get-Content "
                "-Encoding utf8 in PowerShell.")
WRITE_AS_UTF8 = ("Run the program with UTF-8 output, such as PYTHONUTF8=1 for Python or chcp.com 65001 "
                 "before a Windows program.")
DROPPED = ("persistedOutputPath", "persistedOutputSize")


def patterns_problem(value: Any) -> str | None:
    """What is wrong in an error_patterns value: each name maps to a list of regular expressions."""
    for name, listed in value.items():
        if not isinstance(listed, list) or not all(isinstance(item, str) for item in listed):
            return f"{name} must map to a list of regular expressions."
        for item in listed:
            try:
                re.compile(item)
            except re.error as error:
                return f"{name} holds a pattern that does not compile: {item}: {error}."
    return None


def exits_problem(value: Any) -> str | None:
    """What is wrong in a benign_exits value: each command maps exit codes, as strings, to their meaning."""
    for name, codes in value.items():
        if not isinstance(codes, dict) or not all(code.isdigit() and isinstance(meaning, str)
                                                  for code, meaning in codes.items()):
            return f"{name} must map exit codes, such as \"1\", to what each means."
    return None


def counted(errors: Sequence[output.ErrorLine]) -> str:
    kinds = Counter(error.kind for error in errors)
    return ", ".join(f"{count} {kind}" for kind, count in kinds.items())


def reporting(count: int) -> str:
    return f"{output.plural(count, 'line')} that {'reports' if count == 1 else 'report'} errors"


class Reading:
    """One shell result, read once: the command, its exit code and what it printed at construction, and the
    saved output and the lines that report errors when a reader first asks for them."""

    def __init__(self, event: Event, ctx: Context, options: Mapping[str, Any]) -> None:
        self.event, self.ctx, self.options = event, ctx, options
        self.command = event.command or ""
        self.bash = event.tool is Tool.BASH
        self.found = shell.scan(self.command) if self.bash else None
        self.simples = shell.commands(self.command) if self.bash else pwsh.commands(self.command)
        self.failed = event.kind is HookEvent.POST_TOOL_USE_FAILURE
        self.response = {} if self.failed else dict(event.tool_response or {})
        self.code, self.text = self.printed()

    def printed(self) -> tuple[int | None, str]:
        """The exit code and what the command printed: the text after a failed call's Exit code line, or the
        stdout and stderr of a call that ran."""
        if self.failed:
            error = self.event.error or ""
            code = output.exit_code(error)
            return code, error.partition("\n")[2] if code is not None else ""
        stderr = str(self.response.get("stderr") or "")
        return 0, str(self.response.get("stdout") or "") + (f"\n{stderr}" if stderr else "")

    @cached_property
    def saved(self) -> str | None:
        """The file Claude Code saved a long output to, when it is in this session's tool-results folder."""
        found = output.saved_path(self.response or {"stdout": self.text})
        if found and not output.in_tool_results(found, claude_folder(self.ctx.env), self.event.session_id):
            log.debug("io-guard left %s unread: it is not in this session's tool-results folder", found)
            return None
        return found

    @cached_property
    def stored(self) -> tuple[int, str | None]:
        """The size and text of the saved output. The text is None with no saved file, or one missing or
        larger than max_bytes."""
        if self.saved is None:
            return 0, None
        path = Path(self.saved)
        found = self.ctx.fs.stat(path)
        if found is None or found.size > self.options["max_bytes"]:
            return 0, None
        try:
            return found.size, self.ctx.fs.read_bytes(path).decode("utf-8", "replace")
        except OSError:
            return 0, None

    @property
    def size(self) -> int:
        return self.stored[0]

    @property
    def whole(self) -> str | None:
        return self.stored[1]

    @property
    def full(self) -> str:
        """The whole output: the saved file's text when there is one, else what the call printed."""
        return self.text if self.whole is None else self.whole

    @cached_property
    def errors(self) -> tuple[output.ErrorLine, ...]:
        """The output's lines that report errors, none when every command only reads files or logs."""
        quoting = all(simple.name in QUIET or shell.matching(simple, self.options["readers"])
                      for simple in self.simples)
        patterns = output.compiled(self.options["error_patterns"])
        return () if quoting else output.error_lines(self.full, patterns)

    def label(self, entries: Sequence[str]) -> tuple[int, str] | None:
        """The index and label of the first simple command that runs one of entries."""
        return next(((index, label) for index, simple in enumerate(self.simples)
                     if (label := shell.matching(simple, entries))), None)

    def result(self, code: Code, message: str, fix: str | None = None, **fields: Any) -> Result:
        advice = None if fix is None else Fix(self.event.tool_name, {}, fix)
        return Result.of(code, message, self.event.tool_name, self.ctx.platform.os, fix=advice, **fields)

    def shown(self, errors: Sequence[output.ErrorLine]) -> str:
        width, limit = self.options["line_chars"], self.options["shown_errors"]
        numbers = len(f"{errors[min(limit, len(errors)) - 1].number:,}")
        return "\n".join(f"{error.number:>{numbers},}| {error.text[:width]}" for error in errors[:limit])

    def budget(self) -> Result | None:
        """A well-formed command over learn_from_bytes that the Bash tool's bash read as ending inside a
        quote: the tool cut it, so the session's budget drops below its length. Where no cut is known, on
        macOS, the budget drops at the second such command."""
        if not (self.bash and self.failed and CUT.search(self.text)):
            return None
        length = shell.budget_length(self.command)
        whole = (not self.found.unterminated and not self.found.carriage_returns
                 and all(heredoc.terminated for heredoc in self.found.heredocs))
        if length <= self.options["learn_from_bytes"] or not whole:
            return None
        session = self.ctx.session
        with session.lock:
            if self.ctx.platform.macos and session.first_cut is None:
                session.first_cut = length
                return self.result(Code.TRANSPORT_BUDGET,
                                   f"Bash read this well-formed {length:,}-byte command as ending inside a "
                                   f"quote. No cut is known on macOS, so io-guard lowers this session's "
                                   f"budget only after a second one.", severity=Severity.WARNING,
                                   evidence={"bytes": length})
            cuts = [length - 1, session.budget_override, None if session.first_cut is None
                    else session.first_cut - 1]
            learned = min(cut for cut in cuts if cut is not None)
            session.budget_override = learned
        return self.result(Code.TRANSPORT_BUDGET,
                           f"The Bash tool on this machine cut this well-formed {length:,}-byte command, so "
                           f"bash read it as ending inside a quote. io-guard now keeps this session's "
                           f"commands to {learned:,} bytes.", severity=Severity.WARNING,
                           evidence={"bytes": length, "budget": learned})

    def saved_output(self) -> tuple[Result, dict] | None:
        """OUTPUT_SAVED, and the output replaced by its first and last lines and its error lines."""
        if self.failed or self.whole is None:
            return None
        head, tail = self.options["head_lines"], self.options["tail_lines"]
        lines = self.whole.count("\n") + (0 if self.whole.endswith("\n") else 1)
        marked = self.errors[:self.options["shown_errors"]]
        body = output.excerpt(self.whole, head, tail, marked, self.options["line_chars"])
        path = Path(self.saved).as_posix()
        stdout = f"[io-guard: the whole output is in {path}]\n{body}"
        kept = {key: value for key, value in self.response.items() if key not in DROPPED}
        errors = f", the {reporting(len(marked))}" if marked else ""
        result = self.result(Code.OUTPUT_SAVED,
                             f"The output was {self.size / 1024:,.1f} KB in {output.plural(lines, 'line')}, "
                             f"so io-guard shows its first {head} lines{errors} and its last {tail}.",
                             f"Read {path} with offset and limit for the rest.",
                             evidence={"path": path, "lines": lines, "bytes": self.size})
        return result, {**kept, "stdout": stdout}

    def hiding_pipe(self) -> str | None:
        """The last command of the pipe that gave a Bash command exit code 0, or None when no pipe did, or
        when an echo or printf of $?, after some other command and before that pipe, already put that
        command's exit code in the output."""
        if not self.bash or self.failed or shell.pipefail(self.command):
            return None
        lines = shell.pipelines(self.command)
        if not lines or len(lines[-1].commands) < 2:
            return None
        printed = any(simple.name in ("echo", "printf") and any("$?" in word for word in simple.words[1:])
                      for line in lines[1:-1] for simple in line.commands)
        return None if printed else lines[-1].commands[-1].name

    def reported(self) -> Result | None:
        """PIPE_HIDES_EXIT when a pipe gave a command that reports errors exit code 0, and ERRORS_IN_OUTPUT
        when the errors sit in a long or saved output."""
        if not self.errors:
            return None
        found = f"The output has {reporting(len(self.errors))} ({counted(self.errors)})"
        kinds = {"kinds": dict(Counter(error.kind for error in self.errors))}
        last = self.hiding_pipe()
        if last is not None:
            return self.result(Code.PIPE_HIDES_EXIT, f"{found}, and exit code 0 is {last}'s, the last "
                               f"command of the pipe:\n{self.shown(self.errors)}",
                               "Read the output for the result, not the exit code.", evidence=kinds)
        if self.full.count("\n") + 1 <= self.options["short_lines"] and self.whole is None:
            return None
        return self.result(Code.ERRORS_IN_OUTPUT, f"{found}, first:\n{self.shown(self.errors)}",
                           evidence=kinds)

    def benign(self) -> Result | None:
        """EXIT_BENIGN when every command that can have set the exit code either gives that code as an
        answer, such as grep's 1 for no match, or never fails without a message, and the output reports no
        error."""
        if not (self.bash and self.failed and self.code) or self.errors or SHELL_ERROR.search(self.text):
            return None
        exits: Mapping[str, Mapping[str, str]] = self.options["benign_exits"]
        candidates, answers = shell.exit_candidates(self.command), []
        for simple in candidates:
            name = next((name for name in exits if shell.matching(simple, [name])), None)
            meaning = None if name is None else exits[name].get(str(self.code))
            if meaning is not None:
                answers.append((simple, name, meaning))
            elif simple.name not in QUIET:
                return None
        if not answers:
            return None
        named = ", or ".join(dict.fromkeys(f"{name} gives when {meaning}" for _, name, meaning in answers))
        message = f"Exit code {self.code} is the answer {named}, not a failure."
        after = answers[-1][1]
        if len(answers) == 1 and answers[0][0] is not candidates[0]:
            message += " The commands after it in the && chain did not run."
            fix = (f"Join them with ; instead of &&, or put || true after {after}, when that answer is "
                   f"expected.")
        else:
            fix = f"Nothing to fix. Put || true after {after} when that answer is expected."
        return self.result(Code.EXIT_BENIGN, message, fix, evidence={"exit_code": self.code})

    def garbled(self) -> Result | None:
        """MOJIBAKE when the output holds U+FFFD, or UTF-8 a console showed in its own code page."""
        if "\x00" in self.full:
            return None
        found = output.mojibake(self.full, self.options["code_pages"])
        if not (found.replaced or found.garbled):
            return None
        parts = []
        if found.garbled:
            parts.append(f"{output.plural(found.garbled, 'run')} of UTF-8 read in a Windows code page, such "
                         f"as {found.example} for {found.meant}")
        if found.replaced:
            parts.append(f"{output.plural(found.replaced, 'U+FFFD character')}, each where bytes were not "
                         f"UTF-8")
        fix = (READ_AS_UTF8 if found.garbled else WRITE_AS_UTF8) + " Copy none of that text into a file."
        return self.result(Code.MOJIBAKE, f"The output holds {' and '.join(parts)}.", fix,
                           evidence={"garbled": found.garbled, "replaced": found.replaced})

    def stale(self) -> Result | None:
        """STALE_BINARY for a run of what a build made, after the session's last build failed. A command that
        builds records whether its build failed."""
        build, run = self.label(self.options["builds"]), self.label(self.options["runs"])
        session = self.ctx.session
        before = session.last_failed_build
        if build is not None:
            broke = any(error.kind in FAILED_BUILD for error in self.errors)
            with session.lock:
                if broke:
                    session.last_failed_build = build[1]
                elif not self.failed:
                    session.last_failed_build = None
            if run is not None and run[0] > build[0]:
                before = build[1] if broke else None
        if run is None or before is None:
            return None
        return self.result(Code.STALE_BINARY, f"The last build in this session, {before}, failed, so "
                           f"{run[1]} ran what the build before it made.",
                           f"Fix the build and build again before trusting what {run[1]} reports.")


def options() -> dict[str, ConfigKey]:
    return {
        "error_patterns": ConfigKey(dict, ERROR_PATTERNS, "Regular expressions, grouped by kind, for the "
                                    "output lines that report an error. A line counts when one matches from "
                                    "its start.", shape=patterns_problem, project_regex=True),
        "benign_exits": ConfigKey(dict, BENIGN_EXITS, "For a command, by its first words, the exit codes "
                                  "that give an answer rather than a failure, and what each means.",
                                  shape=exits_problem),
        "readers": ConfigKey(list, READERS, "Commands whose output quotes a file or a log, such as grep or "
                             "tail, each as its first words. Error lines in their output count for nothing. "
                             "A project's list replaces it."),
        "builds": ConfigKey(list, list(shell.BUILDS), "Commands that build a program, each as its first "
                            "words. One that prints compiler or build errors marks the session's build as "
                            "failed. A project's list replaces it."),
        "runs": ConfigKey(list, RUNS, "Commands that run what a build made without building it, each as its "
                          "first words. One after a failed build gets a STALE_BINARY warning. A project's "
                          "list replaces it."),
        "short_lines": ConfigKey(int, 50, "Lines of output a command may print before its error lines are "
                                 "counted and quoted."),
        "head_lines": ConfigKey(int, 20, "Lines from the start of a saved output shown in its place."),
        "tail_lines": ConfigKey(int, 20, "Lines from the end of a saved output shown in its place."),
        "shown_errors": ConfigKey(int, 5, "Error lines a message quotes."),
        "line_chars": ConfigKey(int, 300, "Characters of each quoted line."),
        "max_bytes": ConfigKey(int, 16 * 1024 * 1024, "The largest saved output io-guard reads, in bytes."),
        "code_pages": ConfigKey(list, ["cp1252", "cp1250"], "Code pages whose view of UTF-8 counts as "
                                "mojibake. A project's list replaces it."),
        "learn_from_bytes": ConfigKey(int, 5000, "Bytes a well-formed Bash command must pass before an "
                                      "unexpected EOF lowers the session's transport budget."),
    }


class CommandResults(Check):
    meta = CheckMeta(
        id="shell.results", layer=Layer.OUTPUT,
        events=frozenset({HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL}), platforms=EVERY_PLATFORM,
        severity=Severity.WARNING, cost=Cost.MEDIUM, reads=frozenset({"command"}), writes=frozenset(),
        after=frozenset(), config=options(),
        codes=frozenset({Code.EXIT_BENIGN, Code.ERRORS_IN_OUTPUT, Code.OUTPUT_SAVED, Code.MOJIBAKE,
                         Code.PIPE_HIDES_EXIT, Code.STALE_BINARY, Code.TRANSPORT_BUDGET}),
        description="Labels exit codes that are answers, summarises error lines and saved output, and flags "
                    "mojibake, a pipe that hides a failure and a run after a failed build.")

    def run(self, event: Event, ctx: Context) -> Decision:
        reading = Reading(event, ctx, self.options)
        learned = reading.budget()
        if learned is not None:
            return Decision(self.meta.id, Verdict.ALLOW, results=(learned,))
        saved = reading.saved_output()
        told = (None if saved is None else saved[0], reading.benign(), reading.reported(), reading.garbled(),
                reading.stale())
        found = [result for result in told if result is not None]
        if not found:
            return Decision.observe(self.meta.id)
        return Decision(self.meta.id, Verdict.ALLOW, results=tuple(found),
                        output_replacement=None if saved is None else saved[1])
