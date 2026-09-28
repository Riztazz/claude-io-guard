"""io.edit, io.splice and io.append: changes to one file, made in memory and written once, in the file's own
bytes.

Agents rebuilt all three in scratch scripts again and again: a batch of edits that asserts each anchor
matches once, a splice between two markers, and a dated entry appended to a log. Each tool finds its places
the way the Edit tool does, with every line ending read as LF, and changes the file's own text through
lib.edits: untouched lines keep their endings, new lines take the file's ending, new text takes the indent of
the lines around it, and the file keeps its BOM and encoding. Nothing is written unless every place matched
(ANC-3), and the write is one atomic replace (BYT-9). A thread lock per file and lib.locks.file_lock hold the
file from the read to the replace, so two subagents, or two sessions' servers, that change one file take
turns (D13). A failed anchor gets task 20's diagnosis, and expect_hash refuses a change to a file that changed
since the agent read its hash. Claude Code does not see an io tool's write as its own, so every result says
to Read the file before the next built-in Edit.
"""
import dataclasses
import hashlib
import tempfile
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from ioguard.checks.diagnose import Diagnosis, Failed, Wording
from ioguard.lib import anchors, edits, editorconfig, locks, paths
from ioguard.lib.context import Context
from ioguard.lib.profile import BOM_CHAR, Bom, Profile, profile
from ioguard.lib.results import Code, Fix, Result, Severity, callable_name
from ioguard.mcp.toolspec import ToolCall, ToolFailure, ToolSpec, doc

NOTE = "The built-in Edit tool needs a fresh Read of this file before its next use."
LOCKS = paths.LockTable()
HASH_DOC = ("Optional. A sha256 of the file from io.read, which refuses the call if any byte of the file "
            "changed since. Leave it out when only the text the call names matters.")


@dataclass(frozen=True)
class EditPair:
    old_string: str = doc("The text to replace. It must appear exactly once in the text the edits before it "
                          "leave.")
    new_string: str = doc("The text to put in its place.")


@dataclass(frozen=True)
class EditInput:
    path: str = doc("The file, absolute or from the project folder.")
    edits: list[EditPair] = doc("The edits, made in order. If one old_string is missing or appears more "
                                "than once, no edit is written.")
    expect_hash: str = doc(HASH_DOC, default="")


@dataclass(frozen=True)
class SpliceInput:
    path: str = doc("The file, absolute or from the project folder.")
    start: str = doc("The text that marks the start. It must appear exactly once in the file, and it stays.")
    end: str = doc("The text that marks the end: its first appearance after start. It stays unless "
                   "include_end is true.")
    text: str = doc("The text to put between the two markers, exactly as given.")
    include_end: bool = doc("Replace the end marker too.", default=False)
    expect_hash: str = doc(HASH_DOC, default="")


@dataclass(frozen=True)
class AppendInput:
    path: str = doc("The file, absolute or from the project folder.")
    text: str = doc("The lines to add at the end of the file.")
    wrap_column: int | None = doc("Break lines longer than this many characters at spaces. 0 keeps them "
                                  "whole. Left out, it is the file's .editorconfig max_line_length, if any.",
                                  default=None)
    date_prefix: bool = doc("Start the text with today's date and a dash, such as 2026-09-28 - , after any "
                            "list marker.", default=False)
    expect_hash: str = doc(HASH_DOC, default="")


@dataclass(frozen=True)
class Place:
    first_line: int
    last_line: int

    def shown(self) -> str:
        if self.first_line == self.last_line:
            return f"{self.first_line:,}"
        return f"{self.first_line:,}-{self.last_line:,}"


@dataclass(frozen=True)
class ChangeOutput:
    path: str = doc("The file, as a path with forward slashes.")
    profile: str = doc("The file's endings, BOM, encoding, indent and lines after the change.")
    changed: bool = doc("False when the file already held what was asked, so nothing was written.")
    lines: list[Place] = doc("Where each piece of new text sits in the file now, counted from 1.")
    sha256: str = doc("The SHA-256 of the file's bytes after the call.")
    indented: list[str] = doc("The new text io-guard indented as the lines around it are.")
    note: str = doc("What the built-in Edit tool needs before its next use of this file.")

    def render(self) -> str:
        where = ", ".join(place.shown() for place in self.lines)
        single = len(self.lines) == 1 and self.lines[0].first_line == self.lines[0].last_line
        head = "already as asked, so nothing was written"
        if self.changed:
            head = f"{'line' if single else 'lines'} {where} changed"
        return "\n".join([f"{self.path}: {head}. {self.profile}, sha256 {self.sha256}.", *self.indented,
                          self.note])


@dataclass(frozen=True)
class Loaded:
    """A file's text as its bytes hold it, without its BOM, and what writing it back needs."""
    path: Path
    data: bytes
    found: Profile
    text: str

    def encoded(self, text: str) -> bytes:
        """text in the file's encoding, with the file's BOM. UnicodeEncodeError for a character the file's
        code page does not hold."""
        return ((BOM_CHAR if self.found.bom is not Bom.NONE else "") + text).encode(self.found.codec)


def refused(code: Code, message: str, tool: str, path: Path, ctx: Context, fix: Fix | None = None,
            **evidence) -> ToolFailure:
    return ToolFailure(Result.of(code, message, tool, ctx.platform.os, severity=Severity.REFUSED, file=path,
                                 fix=fix, evidence=evidence))


@contextmanager
def held(path: Path, ctx: Context, tool: str) -> Iterator[None]:
    """path held against the process's other threads, then against every other io-guard process, for the
    with block. A holder that keeps it past io.edit.wait_ms refuses the call."""
    wait_s = ctx.config.get("io.edit.wait_ms") / 1000
    busy = refused(Code.FILE_LOCKED, f"Another io-guard call held {path.name} for {wait_s:g} seconds, so "
                   f"{tool} wrote nothing.", tool, path, ctx,
                   Fix(callable_name(tool), {}, f"Call {callable_name(tool)} again once that call is done."))
    lock = LOCKS.lock(path)
    if not lock.acquire(timeout=wait_s):
        raise busy
    try:
        with ExitStack() as stack:
            try:
                stack.enter_context(locks.file_lock(path, lock_folder(ctx), wait_s))
            except TimeoutError:
                raise busy from None
            yield
    finally:
        lock.release()


def lock_folder(ctx: Context) -> Path:
    """The plugin data folder, or without one a folder in the system's temporary folder, which every
    io-guard process without a data folder shares."""
    return ctx.data_dir or Path(tempfile.gettempdir()) / "io-guard"


def load(path: Path, ctx: Context, tool: str, expect_hash: str) -> Loaded:
    """The file's bytes and text, or the refusal that names why the tool cannot change it."""
    name = path.name
    found = ctx.fs.stat(path)
    if found is None:
        glob = Fix("Glob", {"pattern": f"**/{name}"},
                   f"Glob for **/{name} to find where it is, or create it with Write.")
        raise refused(Code.PATH_NOT_FOUND, f"{path.as_posix()} does not exist, so {tool} wrote nothing.",
                      tool, path, ctx, glob)
    limit = ctx.config.get("io.edit.max_bytes")
    if found.size > limit:
        raise refused(Code.READ_TOO_LARGE, f"{name} holds {found.size:,} bytes, more than {tool} changes, "
                      f"{limit:,}.", tool, path, ctx, Fix("Edit", {"file_path": str(path)},
                                                          "Change it with the Edit tool."))
    if found.readonly:
        raise refused(Code.READ_ONLY, f"{name} is read-only, so {tool} wrote nothing.", tool, path, ctx)
    see = Fix(callable_name("io.read"), {"path": str(path)},
              f"Call {callable_name('io.read')} to see its bytes.")
    try:
        data = ctx.fs.read_bytes(path)
    except OSError as error:
        raise refused(Code.PATH_NOT_FOUND, f"{name} cannot be read as a file: {error.strerror or error}.",
                      tool, path, ctx, see) from None
    actual = hashlib.sha256(data).hexdigest()
    if expect_hash and expect_hash.strip().lower() != actual:
        read = callable_name("io.read")
        raise refused(Code.STALE_VIEW, f"{name} changed since the read that gave expect_hash, so {tool} "
                      f"wrote nothing.", tool, path, ctx,
                      Fix(read, {"path": str(path)}, f"Call {read} for its lines and sha256, then call "
                                                      f"{callable_name(tool)} again with that expect_hash."),
                      expected=expect_hash, actual=actual)
    found_profile = profile(data)
    if found_profile.binary:
        text_only = Fix(callable_name(tool), {},
                        "Call it on a text file. A binary file changes through the program that makes it.")
        raise refused(Code.ENCODING_INVALID, f"{name} holds NUL bytes, so {tool} reads it as binary and "
                      f"wrote nothing.", tool, path, ctx, text_only)
    try:
        text = data.decode(found_profile.codec)
        whole = text.encode(found_profile.codec) == data
    except UnicodeError:
        whole = False
    if not whole:
        raise refused(Code.ENCODING_INVALID, f"{name} does not read back as the same bytes in "
                      f"{found_profile.codec}, so {tool} wrote nothing.", tool, path, ctx, see)
    return Loaded(path, data, found_profile, text.removeprefix(BOM_CHAR))


def written(loaded: Loaded, text: str, places: list[Place], indented: list[str], ctx: Context,
            tool: str) -> ChangeOutput:
    """The new text written over the file when it changed anything, and the result that says so."""
    path = loaded.path
    try:
        data = loaded.encoded(text)
    except UnicodeEncodeError as error:
        character = error.object[error.start]
        raise refused(Code.ENCODING_INVALID, f"{path.name} is {loaded.found.codec}, which cannot hold "
                      f"U+{ord(character):04X} from the new text, so {tool} wrote nothing.", tool, path, ctx,
                      Fix(callable_name(tool), {}, f"Use only characters {loaded.found.codec} holds, such "
                                                   f"as ASCII, in the new text.")) from None
    if data != loaded.data:
        try:
            ctx.fs.write_atomic(path, data)
        except PermissionError:
            try:
                holding = ", ".join(f"{each.name} (process {each.pid})" for each in ctx.fs.holders(path))
            except OSError:
                holding = ""
            raise refused(Code.FILE_LOCKED, f"{holding or 'Another program'} holds {path.name} open, so "
                          f"{tool} could not replace it and wrote nothing.", tool, path, ctx) from None
    return ChangeOutput(path.as_posix(), profile(data).line(), data != loaded.data, places,
                        hashlib.sha256(data).hexdigest(), indented, NOTE)


def indent_notes(indented: tuple[tuple[int, str], ...], what: str) -> list[str]:
    return [f"io-guard indented {what.format(index + 1)} with {style}, as the lines around it are."
            for index, style in indented]


def diagnosed(tool: str, wording: Wording, tool_input: dict, text: str, call: ToolCall,
              ambiguous: bool) -> Result:
    """Task 20's diagnosis of a place that did not match once, in text the tool had not written yet."""
    failed = Failed(tool, tool_input, "", call.cwd, wording)
    diagnosis = Diagnosis(failed, call.context, {}, contents=text.encode("utf-8"))
    found = diagnosis.anchor_ambiguous() if ambiguous else diagnosis.anchor_missing()
    if found:
        result = found[0]
    else:
        result = Result.of(Code.ANCHOR_NOT_FOUND, f"{wording.subject} is empty, so it names no place.", tool,
                           call.context.platform.os, file=diagnosis.path,
                           fix=Fix(wording.retry, {}, f"Give {wording.field} the text it stands for."))
    return dataclasses.replace(result, severity=Severity.REFUSED,
                               message=f"{tool} wrote nothing. {result.message}")


def edit(given: EditInput, call: ToolCall) -> ChangeOutput:
    tool, ctx = "io.edit", call.context
    path = paths.normalise(given.path, call.cwd, ctx.platform)
    with held(path, ctx, tool):
        loaded = load(path, ctx, tool, given.expect_hash)
        changes = [edits.Change(pair.old_string, pair.new_string) for pair in given.edits]
        made = edits.apply(loaded.text, changes, loaded.found.new_eol, loaded.found.indent.width)
        if isinstance(made, edits.Missed):
            raise ToolFailure(missed_edit(given, made, loaded, call))
        places = [Place(first, last) for first, last in made.lines]
        return written(loaded, made.text, places, indent_notes(made.indented, "the new_string of edit {}"),
                       ctx, tool)


def missed_edit(given: EditInput, miss: edits.Missed, loaded: Loaded, call: ToolCall) -> Result:
    """The diagnosis of the edit whose old_string is missing or repeated, with a fix that is the whole
    io.edit call again, that edit corrected."""
    number = miss.index + 1
    after = {1: "", 2: ", looked for after edit 1,"}.get(number, f", looked for after edits 1-{miss.index},")
    retry = callable_name("io.edit")
    pair = given.edits[miss.index]
    wording = Wording(f"old_string of edit {number}{after}", "old_string", retry, replace_all=False)
    single = {"path": given.path, "old_string": pair.old_string, "new_string": pair.new_string}
    result = diagnosed("io.edit", wording, single, miss.text, call, ambiguous=len(miss.matches) > 1)
    if result.fix is None or "old_string" not in result.fix.input:
        return result
    pairs = [dataclasses.asdict(each) for each in given.edits]
    pairs[miss.index]["old_string"] = result.fix.input["old_string"]
    whole = {"path": given.path, "edits": pairs, **({"expect_hash": given.expect_hash}
                                                     if given.expect_hash else {})}
    return dataclasses.replace(result, fix=dataclasses.replace(result.fix, input=whole))


def splice(given: SpliceInput, call: ToolCall) -> ChangeOutput:
    tool, ctx = "io.splice", call.context
    path = paths.normalise(given.path, call.cwd, ctx.platform)
    with held(path, ctx, tool):
        loaded = load(path, ctx, tool, given.expect_hash)
        view = anchors.edit_view(loaded.text)
        start = anchors.find(view, anchors.edit_view(given.start))
        if len(start) != 1:
            raise ToolFailure(missed_marker(given, "start", loaded.text, call, ambiguous=len(start) > 1))
        wanted = anchors.edit_view(given.end)
        at = view.find(wanted, start[0].end) if wanted else -1
        if at < 0:
            raise ToolFailure(missed_end(given, path, view, loaded.text, call))
        end = at + len(wanted) if given.include_end else at
        made = edits.change(loaded.text, start[0].end, end, given.text, loaded.found.new_eol,
                            loaded.found.indent.width)
        after = anchors.edit_view(made.text)
        last = anchors.line_of(after, max(made.start, made.end - 1))
        place = Place(anchors.line_of(after, made.start), last)
        notes = [] if made.indented is None else indent_notes(((0, made.indented),), "the text")
        return written(loaded, made.text, [place], notes, ctx, tool)


def splice_wording(marker: str) -> Wording:
    return Wording(f"the {marker} marker", marker, callable_name("io.splice"), replace_all=False)


def missed_marker(given: SpliceInput, marker: str, text: str, call: ToolCall, ambiguous: bool) -> Result:
    return diagnosed("io.splice", splice_wording(marker), dataclasses.asdict(given), text, call, ambiguous)


def missed_end(given: SpliceInput, path: Path, view: str, text: str, call: ToolCall) -> Result:
    """The end marker is not after the start marker: found only before it, or not at all."""
    wanted = anchors.edit_view(given.end)
    before = anchors.find(view, wanted) if wanted else ()
    if not before:
        return missed_marker(given, "end", text, call, ambiguous=False)
    retry = callable_name("io.splice")
    lines = ", ".join(f"{match.first_line:,}" for match in before[:5])
    where = f"line {lines}" if len(before) == 1 else f"lines {lines}"
    fix = Fix(retry, {}, f"Call {retry} with an end marker that comes after the start marker.")
    return Result.of(Code.ANCHOR_NOT_FOUND, f"io.splice wrote nothing. The end marker is in {path.name} only "
                     f"before the start marker, on {where}.", "io.splice", call.context.platform.os,
                     severity=Severity.REFUSED, file=path, fix=fix)


def append(given: AppendInput, call: ToolCall) -> ChangeOutput:
    tool, ctx = "io.append", call.context
    path = paths.normalise(given.path, call.cwd, ctx.platform)
    with held(path, ctx, tool):
        loaded = load(path, ctx, tool, given.expect_hash)
        addition = given.text
        if given.date_prefix:
            lead = edits.LIST_LEAD.match(addition)[0]
            day = ctx.clock.now().astimezone().date().isoformat()
            addition = f"{lead}{day} - {addition[len(lead):]}"
        if not addition.strip("\r\n"):
            return written(loaded, loaded.text, [], [], ctx, tool)
        column = given.wrap_column if given.wrap_column is not None else max_line_length(path, ctx)
        if column > 0:
            addition = edits.wrapped(addition, column)
        before = anchors.edit_view(loaded.text)
        text = edits.appended(loaded.text, addition, loaded.found.new_eol)
        after = anchors.edit_view(text)
        first = before.count("\n") + (1 if before and not before.endswith("\n") else 0) + 1
        last = after.count("\n") + (0 if after.endswith("\n") else 1)
        return written(loaded, text, [Place(min(first, last), last)], [], ctx, tool)


def max_line_length(path: Path, ctx: Context) -> int:
    """The .editorconfig max_line_length that applies to path, or 0 when none does."""
    def read(file: Path) -> str | None:
        try:
            return ctx.fs.read_bytes(file).decode("utf-8", "replace")
        except OSError:
            return None
    value = editorconfig.properties(path, read).get("max_line_length", "")
    return int(value) if value.isdigit() else 0


SPECS = (
    ToolSpec("io.edit", "Edit a file in several places at once",
             "Makes several edits in one file in one call, all or nothing: each old_string must appear "
             "exactly once, and the file keeps its line endings, BOM, encoding and indent. Use it for more "
             "than one change to a file, or where the built-in Edit mangles CRLF or a BOM.",
             EditInput, ChangeOutput, read_only=False, destructive=True, idempotent=False, handler=edit),
    ToolSpec("io.splice", "Replace the text between two markers",
             "Replaces everything between a start marker and the first end marker after it, in the file's "
             "own line endings. Use it to rewrite a block without quoting the old block as an anchor.",
             SpliceInput, ChangeOutput, read_only=False, destructive=True, idempotent=False, handler=splice),
    ToolSpec("io.append", "Append lines to a file",
             "Adds lines at the end of a file in its own line endings, wrapped at a column and dated if "
             "asked. Use it for a log or a changelog entry, where an Edit anchor would be the file's last "
             "lines.",
             AppendInput, ChangeOutput, read_only=False, destructive=False, idempotent=False, handler=append),
)
