"""io.run, io.status and io.read_log: a program run from an argument list or a code body with no shell in
between, its state while it runs in the background, and the lines a log gained since the last look.

49% of Bash calls run Python, and the shell string between the model and the program is where content gets
mangled (SHW-2, SHW-4). io.run takes the program as an argument list, or a code body it writes to a file
byte for byte and runs with the interpreter for its language, so no quoting layer stands in the way on either
platform. It holds the call to the user's Bash and PowerShell deny and ask rules first (D14, run.rules). The
program runs in the folder asked for, with task 10's UTF-8 variables, an empty stdin, and its stdout and
stderr in one log. A run to its end answers the exit code, labelled as shell.results labels a Bash call's,
with the lines that report errors and the last lines. A background run answers a handle at once, and
io.status reports on the process itself, never on its log (RUN-2). io.read_log returns the whole lines a log
gained since the last call, less the config's noise_patterns (OUT-11).
"""
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from ioguard.checks.command_results import compiled
from ioguard.checks.run_rules import judge, said
from ioguard.lib import output, paths, proc, rules, runs
from ioguard.lib.context import Context
from ioguard.lib.results import Code, Fix, Result, Severity, callable_name
from ioguard.mcp import handles
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolFailure, ToolSpec, doc

POLL_S = 0.25
READ_CHUNK = 1024 * 1024
BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class RunInput:
    argv: list[str] = doc("The program and its arguments, one item each, run with no shell. Leave it empty "
                          "to run code instead.", default_factory=list)
    lang: str = doc("The language of code: python, bash, powershell or node.", default="")
    code: str = doc("A program to run instead of argv. io-guard writes it to a file byte for byte, so every "
                    "backslash and quote arrives as written.", default="")
    cwd: str = doc("The folder to run in, absolute or from the project folder. Empty is the project folder.",
                   default="")
    env: dict[str, str] = doc("Variables to set for the program, over the session's own.",
                              default_factory=dict)
    timeout_s: int = doc("Seconds a run to its end may take before io-guard stops it. 0 takes the config's "
                         "io.run.timeout_s, 120 unless set.", default=0)
    background: bool = doc("Start the program and answer at once with a handle for io.status.", default=False)


@dataclass(frozen=True)
class HandleInput:
    handle: str = doc("The handle io.run gave for a background run.")


@dataclass(frozen=True)
class LogInput:
    path: str = doc("The log, absolute or from the project folder.")
    since_line: int | None = doc("Return the lines after this one, counted from 1, and 0 for the whole log. "
                                 "Left out, the lines after the ones the last io.read_log of it returned.",
                                 default=None)


@dataclass(frozen=True)
class ErrorLine:
    line: int
    kind: str
    text: str


@dataclass(frozen=True)
class RunOutput:
    command: str = doc("The command that ran, as one line.")
    state: str = doc("running, ended, timed out or stopped.")
    exit: int | None = doc("The exit code, or null while it runs or when io-guard stopped it.")
    ok: bool = doc("The exit code is 0, or an answer the program gives, which meaning names.")
    meaning: str = doc("What a nonzero exit code means when it is an answer, such as grep's 1 for no match.")
    duration_s: float = doc("Seconds it has run.")
    log_path: str = doc("The log of its stdout and stderr, which io.read_log reads a part at a time.")
    log_bytes: int = doc("The log's size.")
    errors: list[ErrorLine] = doc("The log's lines that report errors, the first few.")
    tail: list[str] = doc("The log's last lines.")
    handle: str = doc("The background run's handle for io.status, or empty.")
    note: str = doc("What to call next.")

    def render(self) -> str:
        code = "" if self.exit is None else f", exit {self.exit}"
        code += f", {self.meaning}" if self.meaning else ""
        head = (f"{self.command}: {self.state}{code}, {self.duration_s:,.1f} s, {self.log_bytes:,} bytes "
                f"of log")
        errors = [f"{error.line:>6}| {error.text}" for error in self.errors]
        parts = [head, *(["Lines that report errors:", *errors] if errors else []),
                 *(["Last lines:", *self.tail] if self.tail else []), f"Log: {self.log_path}", self.note]
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True)
class LogOutput:
    path: str = doc("The log, as a path with forward slashes.")
    first_line: int = doc("The first line returned, counted from 1. 0 when none was.")
    last_line: int = doc("The last line read, which the next call starts after.")
    text: str = doc("The lines, less the ones noise_patterns match.")
    dropped: int = doc("Lines noise_patterns left out.")
    more: bool = doc("Whole lines past last_line wait for the next call.")
    note: str = doc("What changed since the last call, or empty.")

    def render(self) -> str:
        span = f"lines {self.first_line:,}-{self.last_line:,}" if self.first_line else "no new lines"
        dropped = f", {self.dropped:,} left out as noise" if self.dropped else ""
        more = "\nMore lines wait. Call io.read_log again for them." if self.more else ""
        parts = (f"{self.path}: {span}{dropped}", self.note, self.text)
        return "\n".join(part for part in parts if part) + more


def failure(code: Code, message: str, tool: str, ctx: Context, fix: Fix | None = None,
            severity: Severity = Severity.REFUSED) -> ToolFailure:
    return ToolFailure(Result.of(code, message, tool, ctx.platform.os, fix=fix, severity=severity))


def runs_folder(ctx: Context) -> Path:
    return (ctx.data_dir or Path(tempfile.gettempdir()) / "io-guard") / "runs"


def environment(given: RunInput, ctx: Context) -> dict[str, str]:
    """The session's variables, task 10's UTF-8 ones over them, and the call's own over both."""
    options = ctx.config.check_options("session.probe")
    platform_env = options["env_windows"] if ctx.platform.windows else {}
    return {**ctx.env, **options["env"], **platform_env, **given.env}


def meaning_of(argv: tuple[str, ...], exit_code: int | None, ctx: Context) -> str:
    """What exit_code means when shell.results' benign_exits names it for the program argv runs."""
    if not exit_code:
        return ""
    words = rules.named(rules.unwrapped(argv))
    exits = ctx.config.check_options("shell.results")["benign_exits"]
    for name, codes in exits.items():
        if words[:len(name.split())] == name.split() and str(exit_code) in codes:
            return f"the answer {name} gives when {codes[str(exit_code)]}"
    return ""


def reading(pump: proc.Pump, state: str, command: str, handle: str, note: str, ctx: Context) -> RunOutput:
    """The run as it stands: its exit code and meaning, and its log's error lines and last lines."""
    options = ctx.config.check_options("shell.results")
    found = ctx.fs.stat(pump.log)
    size = 0 if found is None else found.size
    limit = options["max_bytes"]
    data = ctx.fs.read_from(pump.log, max(0, size - limit), limit) if size else b""
    text = data.decode("utf-8", "replace")
    width = options["line_chars"]
    found_errors = output.error_lines(text, compiled(options["error_patterns"]))[:options["shown_errors"]]
    errors = [ErrorLine(line.number, line.kind, line.text[:width]) for line in found_errors]
    lines = text.rstrip("\r\n").split("\n") if text else []
    tail = [line.rstrip("\r")[:width] for line in lines[-options["tail_lines"]:]]
    exit_code = pump.exit_code
    meaning = meaning_of(pump.argv, exit_code, ctx)
    return RunOutput(command, state, exit_code, exit_code == 0 or bool(meaning), meaning,
                     round(pump.seconds(), 1), pump.log.as_posix(), size, errors, tail, handle, note)


def checked(given: RunInput, call: ToolCall) -> dict:
    """The call as the rules read it, refused when a deny rule meets it, or when an ask rule does and the
    hook did not put it to the user."""
    ctx = call.context
    fields = {"argv": list(given.argv), "lang": given.lang, "code": given.code}
    found = judge(fields, ctx, call.cwd)
    if found.decision == "deny":
        raise failure(Code.RULE_DENIED, f"io.run did not run {said(found)}.", "io.run", ctx)
    if found.decision == "ask":
        if not ctx.session.take_ask(call.tool_use_id, runs.key(fields), ctx.clock.now()):
            raise failure(Code.RULE_ASKED, f"io.run did not run {said(found)}, and no permission prompt on "
                          f"this call put it to the user.", "io.run", ctx)
    return fields


def run(given: RunInput, call: ToolCall) -> RunOutput:
    ctx, tool = call.context, "io.run"
    if bool(given.argv) == bool(given.code):
        raise InvalidArguments("io.run takes argv, or lang and code, and not both.")
    if given.code and given.lang not in runs.SUFFIXES:
        raise InvalidArguments(f"lang must be one of {', '.join(runs.SUFFIXES)}.")
    fields = checked(given, call)
    folder = runs_folder(ctx) / uuid.uuid4().hex
    body = folder / f"body{runs.SUFFIXES.get(given.lang, '')}"
    argv = runs.argv_of(fields, ctx.probe, ctx.platform, str(body))
    if argv is None:
        raise failure(Code.PATH_NOT_FOUND, f"This machine has no interpreter for {given.lang}.", tool, ctx,
                      Fix(callable_name(tool), {}, "Run the program through argv with its interpreter's full "
                                                   "path."))
    cwd = paths.normalise(given.cwd or ".", call.cwd, ctx.platform)
    if not ctx.fs.exists(cwd):
        raise failure(Code.PATH_NOT_FOUND, f"The folder {cwd.as_posix()} does not exist.", tool, ctx)
    if given.code:
        ctx.fs.make_folders(folder)
        data = given.code.encode("utf-8")
        ctx.fs.write_atomic(body, BOM + data if given.lang == "powershell" else data)
    command = rules.command_text(argv)
    try:
        pump = proc.background(argv, cwd, environment(given, ctx), folder / "output.log")
    except OSError as error:
        raise failure(Code.PATH_NOT_FOUND, f"io.run could not start {argv[0]}: {error.strerror or error}.",
                      tool, ctx, Fix(callable_name(tool), {}, "Name the program by its full path, or check "
                                                              "that it is installed.")) from None
    if given.background:
        return started(pump, command, ctx)
    return waited(pump, command, given.timeout_s or ctx.config.get("io.run.timeout_s"), call)


def started(pump: proc.Pump, command: str, ctx: Context) -> RunOutput:
    handle = handles.STORE.create("run", {"pump": pump, "command": command})
    ttl = timedelta(seconds=ctx.config.get("io.run.handle_ttl_s"))
    pump.when_done(lambda: handles.STORE.settle(handle.id, ttl))
    minutes = ttl.total_seconds() / 60
    note = (f"Call {callable_name('io.status')} with this handle for its state, and "
            f"{callable_name('io.read_log')} with log_path for its output. The handle lasts {minutes:g} "
            f"minutes past the program's end.")
    return reading(pump, "running", command, handle.id, note, ctx)


def waited(pump: proc.Pump, command: str, timeout_s: float, call: ToolCall) -> RunOutput:
    """The run once it ends, or once io-guard stops it past timeout_s or on the client's cancel."""
    deadline = time.monotonic() + timeout_s
    state = "ended"
    while not pump.wait(POLL_S):
        if call.cancel.cancelled:
            pump.stop()
            state = "stopped"
            break
        if time.monotonic() >= deadline:
            pump.stop()
            state = "timed out"
            break
        found = call.context.fs.stat(pump.log)
        call.progress.report(round(pump.seconds(), 1),
                             f"{0 if found is None else found.size:,} bytes of output after "
                             f"{pump.seconds():,.0f} s")
    note = f"io-guard stopped it after {timeout_s:g} seconds." if state == "timed out" else ""
    return reading(pump, state, command, "", note, call.context)


def status(given: HandleInput, call: ToolCall) -> RunOutput:
    ctx = call.context
    try:
        found = handles.STORE.get(given.handle, "run")
    except handles.HandleExpired:
        run_tool = callable_name("io.run")
        raise failure(Code.HANDLE_EXPIRED, f"io-guard holds no run with the handle {given.handle}: it ended "
                      f"over an hour ago, or the server restarted.", "io.status", ctx,
                      Fix(run_tool, {}, f"Call {run_tool} again to start it over. Its log stays in "
                                        f"{runs_folder(ctx).as_posix()}.")) from None
    pump: proc.Pump = found.payload["pump"]
    state = "ended" if pump.done.is_set() else "running"
    return reading(pump, state, found.payload["command"], found.id, "", ctx)


def read_log(given: LogInput, call: ToolCall) -> LogOutput:
    ctx, tool = call.context, "io.read_log"
    path = paths.normalise(given.path, call.cwd, ctx.platform)
    found = ctx.fs.stat(path)
    if found is None:
        raise failure(Code.PATH_NOT_FOUND, f"{path.as_posix()} does not exist.", tool, ctx)
    with ctx.session.lock:
        cursor = ctx.session.read_logs.get(path, (0, 0))
    note = ""
    if given.since_line is not None and given.since_line != cursor[0]:
        cursor = line_offset(path, max(0, given.since_line), found.size, ctx)
    elif cursor[1] > found.size:
        cursor, note = (0, 0), "The log is shorter than at the last call, so io-guard read it from the start."
    line, offset = cursor
    limit = ctx.config.get("io.read.max_bytes")
    chunk = ctx.fs.read_from(path, offset, limit) if offset < found.size else b""
    whole = chunk[:chunk.rfind(b"\n") + 1]
    taken = whole.split(b"\n")[:-1][:ctx.config.get("io.read_log.max_lines")]
    used = sum(len(item) + 1 for item in taken)
    noise = [re.compile(pattern) for pattern in ctx.config.get("noise_patterns")]
    texts = [item.decode("utf-8", "replace").rstrip("\r") for item in taken]
    kept = [f"{line + index + 1:>6}| {text}" for index, text in enumerate(texts)
            if not any(pattern.search(text) for pattern in noise)]
    after = (line + len(taken), offset + used)
    with ctx.session.lock:
        ctx.session.read_logs[path] = after
    more = b"\n" in chunk[used:] or offset + len(chunk) < found.size
    return LogOutput(path.as_posix(), line + 1 if taken else 0, after[0], "\n".join(kept),
                     len(texts) - len(kept), more, note)


def line_offset(path: Path, line: int, size: int, ctx: Context) -> tuple[int, int]:
    """The line and byte where line ends, found by counting line breaks from the start, or the file's last
    whole line when it has fewer."""
    counted, end, offset = 0, 0, 0
    while counted < line and offset < size:
        chunk = ctx.fs.read_from(path, offset, READ_CHUNK)
        if not chunk:
            break
        at = chunk.find(b"\n")
        while at >= 0:
            counted, end = counted + 1, offset + at + 1
            if counted == line:
                return counted, end
            at = chunk.find(b"\n", at + 1)
        offset += len(chunk)
    return counted, end


SPECS = (
    ToolSpec("io.run", "Run a program without a shell",
             "Runs a program from an argument list, or a python, bash, powershell or node body written to a "
             "file byte for byte, with no shell to mangle quotes or backslashes, under the user's Bash and "
             "PowerShell permission rules. Use it for a script body with backslashes or quotes, or a long "
             "run: background returns a handle that lasts one hour past the program's end.",
             RunInput, RunOutput, read_only=False, destructive=True, idempotent=False, handler=run,
             open_world=True),
    ToolSpec("io.status", "Check a background run",
             "Reports whether a background io.run is still running, from the process itself, and its exit "
             "code, errors and last lines once it ends. Use it instead of reading the run's log to tell.",
             HandleInput, RunOutput, read_only=True, destructive=False, idempotent=True, handler=status),
    ToolSpec("io.read_log", "Read the new lines of a log",
             "Returns the whole lines a log gained since the last io.read_log of it, less the config's noise "
             "patterns. Use it to follow a build or server log, or a background run's log_path.",
             LogInput, LogOutput, read_only=True, destructive=False, idempotent=False, handler=read_log),
)
