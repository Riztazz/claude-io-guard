"""io.format: the project's formatter over the lines each file changed since its last commit, and only those,
in the file's own endings.

clang-format over a whole file re-indents code nobody touched and adds namespace closers (BYT-12), and a
LineEnding in its config rewrites the endings of lines it did not change (BYT-3). Agents wrote a script that
ran it over git's changed hunks only, and ran it 128 times. io.format does that job: git diff -U0 HEAD names
the changed lines, a file git has no commit of counts whole, and a call may name its own lines instead. The
command comes from the format key in the user's own config.json, clang-format by default for C and C++ (D24).
It reads the text on stdin and writes the formatted text on stdout. lib.edits.carried lands that text in the
file's own endings, and a run of changes that meets none of the asked lines stays as the file had it. Every
file is formatted in memory before any is written, so a formatter that fails on one file leaves them all as
they were. A dry run stops there and returns each file's diff, for an agent to see what the formatter would
change before any byte does.
"""
import dataclasses
import difflib
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from ioguard.checks.trust_ask import untrusted
from ioguard.lib import commands, edits, paths, proc, text
from ioguard.lib.context import Context
from ioguard.lib.git import GitError
from ioguard.lib.results import Code, Fix, callable_name, render
from ioguard.mcp.in_place import (Loaded, Place, Written, encoded, held, load, places_shown, refused,
                                  write)
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolFailure, ToolSpec, cancelled, doc

TOOL = "io.format"
CALLABLE = callable_name(TOOL)
NOTE = "The built-in Edit tool needs a fresh Read of each changed file before its next use."
DRY_NOTE = f"io.format wrote nothing, because dry_run was set. Call {CALLABLE} again without it to write."
MESSAGE_CHARS = 2_000
DIFF_CHARS = 20_000          # the most of one file's diff a dry run returns


@dataclass(frozen=True)
class FormatInput:
    paths: list[str] = doc("The files to format, absolute or from the project folder.")
    lines: dict[str, list[Place]] = doc(
        "Optional: the lines to format in some of the files, counted from 1, keyed by the path as paths "
        "names it, such as {\"a.cpp\": [{\"first_line\": 10, \"last_line\": 12}]}. A file left out takes the "
        "lines changed since the last commit, or the whole file when git has no commit of it.",
        default_factory=dict)
    dry_run: bool = doc("True returns each file's changes as a diff and writes nothing, to see what the "
                        "formatter would do first.", default=False)


@dataclass(frozen=True)
class FormattedFile:
    path: str = doc("The file, as a path with forward slashes.")
    formatter: str = doc("The program that formatted it, empty when none ran.")
    asked: list[Place] = doc("The lines io.format gave the formatter, counted from 1 before the call.")
    reason: str = doc("Which lines those are, or why no formatter ran.")
    changed: bool = doc("False when no byte of the file changed.")
    lines: list[Place] = doc("Where the formatter changed lines, counted from 1 after the call.")
    left: list[Place] = doc("Lines the formatter changed away from the asked ones, which io.format kept as "
                            "they were.")
    profile: str = doc("The file's endings, BOM, encoding, indent and lines after the call.")
    sha256: str = doc("The SHA-256 of the file's bytes after the call.")
    bytes: int = doc("The file's size in bytes after the call.", default=0)
    diff: str = doc("With dry_run, the file's changes as a unified diff, empty when there are none.",
                    default="")

    def render(self, dry_run: bool = False) -> str:
        if not self.formatter:
            return f"{self.path}: nothing to format, because {self.reason}."
        verb = "would change" if dry_run else "changed"
        head = (f"{self.formatter} {verb} {places_shown(self.lines)}" if self.lines
                else f"{self.formatter} {verb} nothing")
        told = [f"{self.path}: {head}, formatting {places_shown(self.asked)}, {self.reason}. "
                f"{self.profile}, sha256 {self.sha256}."]
        if self.left:
            kept = "would keep" if dry_run else "kept"
            told.append(f"It also {verb} {places_shown(self.left)}, away from those lines, and io.format "
                        f"{kept} them as they were.")
        return " ".join(told) + (f"\n{self.diff}" if self.diff else "")


@dataclass(frozen=True)
class FormatOutput:
    files: list[FormattedFile] = doc("What io.format did to each file, in the order given.")
    note: str = doc("What the built-in Edit tool needs before its next use of a changed file, or, after a "
                    "dry run, that nothing was written.")
    dry_run: bool = doc("True when io.format wrote nothing and each file carries its diff.", default=False)
    waiting: str = doc("PROJECT_COMMANDS_UNTRUSTED when the project names a format command the user has not "
                       "approved, which io.format did not run, else empty.", default="")

    def written_bytes(self) -> int:
        return 0 if self.dry_run else sum(each.bytes for each in self.files if each.changed)

    def render(self) -> str:
        told = [each.render(self.dry_run) for each in self.files]
        noted = [*told, self.note] if self.dry_run or any(each.changed for each in self.files) else told
        return "\n".join([*noted, self.waiting] if self.waiting else noted)


@dataclass(frozen=True)
class Planned:
    """One file's bytes and text after formatting, not written yet, and what its result says."""
    loaded: Loaded
    data: bytes
    text: str
    result: FormattedFile


def format_files(given: FormatInput, call: ToolCall) -> FormatOutput:
    ctx = call.context
    if not given.paths:
        raise InvalidArguments("io.format takes at least one path.")
    targets: dict[str, Path] = {}
    for raw in given.paths:
        path = paths.normalise(raw, call.cwd, ctx.platform)
        targets.setdefault(paths.resolved(path), path)
    named = lines_by_file(given, call, targets)
    notices = (untrusted(ctx.for_file(path), "format", path, TOOL, ctx.platform) for path in targets.values())
    found = next(filter(None, notices), None)
    waiting = "" if found is None else render(found)
    with ExitStack() as stack:
        for key in sorted(targets):
            stack.enter_context(held(targets[key], ctx, TOOL))
        planned = [plan(path, named.get(key, []), ctx) for key, path in targets.items()]
        if call.cancel.cancelled:
            raise ToolFailure(cancelled(TOOL))
        if given.dry_run:
            return FormatOutput([seen(each, Written(each.data, each.data != each.loaded.data), diffed(each))
                                 for each in planned], DRY_NOTE, dry_run=True, waiting=waiting)
        files = [seen(each, write(each.loaded, each.data, ctx, TOOL)) for each in planned]
    return FormatOutput(files, NOTE, waiting=waiting)


def lines_by_file(given: FormatInput, call: ToolCall, targets: dict[str, Path]) -> dict[str, list[Place]]:
    """The lines the call names, keyed as targets is. InvalidArguments for a path paths does not name, or a
    range that runs backwards."""
    found: dict[str, list[Place]] = {}
    for raw, places in given.lines.items():
        key = paths.resolved(paths.normalise(raw, call.cwd, call.context.platform))
        if key not in targets:
            raise InvalidArguments(f"lines names {raw}, which paths does not. Key lines by a path from "
                                   "paths.")
        if any(place.first_line < 1 or place.last_line < place.first_line for place in places):
            raise InvalidArguments(f"Each range of lines for {raw} runs from first_line to a last_line no "
                                   "lower, counted from 1.")
        found.setdefault(key, []).extend(places)
    return found


def seen(each: Planned, done: Written, diff: str = "") -> FormattedFile:
    return dataclasses.replace(each.result, changed=done.changed, profile=done.profile_line(),
                               sha256=done.sha256, bytes=len(done.data), diff=diff)


def diffed(each: Planned) -> str:
    """The file's formatted text against its text now, as a unified diff with one line of context, cut to
    DIFF_CHARS."""
    name = each.loaded.path.name
    found = "\n".join(difflib.unified_diff(each.loaded.text.splitlines(), each.text.splitlines(), name,
                                           f"{name}, formatted", n=1, lineterm=""))
    if len(found) <= DIFF_CHARS:
        return found
    return f"{found[:DIFF_CHARS]}\n(the diff goes on for {len(found) - DIFF_CHARS:,} more characters)"


def plan(path: Path, named: list[Place], ctx: Context) -> Planned:
    """The file's bytes once its lines are formatted, or as they are with the reason no formatter ran. A file
    outside the project takes the config without the project's file."""
    ctx = ctx.for_file(path)
    loaded = load(path, ctx, TOOL)
    unchanged = FormattedFile(path.as_posix(), "", [], "", False, [], [], "", "")
    command = commands.command_for(ctx.config.get("format"), path, ctx.platform)
    if command is None:
        kind = path.suffix or "a file with no extension"
        reason = f"the format key in config.json names no command for {kind}"
        return Planned(loaded, loaded.data, loaded.text, dataclasses.replace(unchanged, reason=reason))
    count = len(edits.lines_of(loaded.text))
    ranges, reason = asked(path, named, count, ctx)
    if not ranges:
        return Planned(loaded, loaded.data, loaded.text, dataclasses.replace(unchanged, reason=reason))
    output = formatted(loaded, commands.filled(command, path, ranges), ctx)
    within = None if ranges == [(1, count)] else ranges
    landed = edits.carried(loaded.text, output, loaded.found.new_eol, within)
    result = dataclasses.replace(unchanged, formatter=Path(command[0]).stem, reason=reason,
                                 asked=[Place(first, last) for first, last in ranges],
                                 lines=[Place(first, last) for first, last in landed.lines],
                                 left=[Place(first, last) for first, last in landed.left])
    return Planned(loaded, encoded(loaded, landed.text, ctx, TOOL), landed.text, result)


def asked(path: Path, named: list[Place], count: int, ctx: Context) -> tuple[list[tuple[int, int]], str]:
    """The lines to format, first and last, and which lines they are. None of them when there is nothing to
    format, with the reason."""
    if count == 0:
        return [], "the file is empty"
    if named:
        ranges = [(place.first_line, min(place.last_line, count)) for place in named
                  if place.first_line <= count]
        if not ranges:
            return [], f"the lines the call named lie past the file's last line, {count:,}"
        return ranges, "the lines the call named"
    try:
        changed = ctx.git.changed_ranges(path)
    except GitError as error:
        raise failed(path, f"git could not name the changed lines of {path.name}: {error}",
                     retry(f"Call {CALLABLE} again with lines, the lines to format."), ctx) from None
    if changed is None:
        return [(1, count)], "the whole file, which git has no commit of"
    ranges = [(each.start, min(each.start + each.count - 1, count)) for each in changed if each.count]
    if not ranges:
        return [], "no line changed since the last commit"
    return ranges, "the lines changed since the last commit"


def formatted(loaded: Loaded, command: tuple[str, ...], ctx: Context) -> str:
    """The format command's output for the file's text, with every CRLF read as LF, as git counts lines."""
    path, name = loaded.path, Path(command[0]).stem
    timeout_s = ctx.config.get("io.format.timeout_s")
    source = loaded.text.replace("\r\n", "\n").encode("utf-8")
    done = proc.run(command, path.parent, ctx.env, timeout_s, stdin=source)
    said = text.head(done.stderr.decode("utf-8", "replace").strip(), MESSAGE_CHARS)
    again = retry(f"Fix what {name} says, then call {CALLABLE} again.")
    if done.start_error:
        raise failed(path, f"io.format could not start {name} for {path.name}: {done.start_error}",
                     retry(f"Ask the user to install {name}, or to name its full path in the format key of "
                           f"their io-guard config.json."), ctx)
    if done.timed_out:
        raise failed(path, f"{name} ran past {timeout_s} seconds on {path.name}, so io-guard stopped it",
                     retry(f"Call {CALLABLE} with fewer lines, or ask the user to raise "
                           f"io.format.timeout_s."), ctx)
    if not done.ok:
        raise failed(path, f"{name} exited {done.exit_code} on {path.name}: {said or 'it printed nothing'}",
                     again, ctx)
    try:
        output = done.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise failed(path, f"{name} printed bytes that are not UTF-8 for {path.name}, at byte {error.start}",
                     again, ctx) from None
    if not output and loaded.text:
        raise failed(path, f"{name} printed nothing for {path.name}, which holds text",
                     retry(f"Ask the user to make the format command for {path.suffix} print the formatted "
                           f"text, not write it over the file."), ctx)
    return output


def retry(words: str) -> Fix:
    return Fix(CALLABLE, {}, words)


def failed(path: Path, message: str, fix: Fix, ctx: Context) -> ToolFailure:
    return refused(Code.FORMAT_FAILED, f"{message}, so io.format wrote nothing.", TOOL, path, ctx, fix)


SPECS = (
    ToolSpec("io.format", "Format the changed lines of files",
             "Runs the project's formatter, such as clang-format with its .clang-format, over the lines each "
             "file changed since the last commit and no others, and keeps the file's line endings, BOM and "
             "encoding. Use it after editing C or C++ files, instead of clang-format on the whole file.",
             FormatInput, FormatOutput, read_only=False, destructive=True, idempotent=True,
             handler=format_files),
)
