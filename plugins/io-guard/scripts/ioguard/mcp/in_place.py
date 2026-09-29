"""A file an io tool changes in place: held against every other io-guard call, loaded as text in its own
encoding, and written back once in its own bytes.

A thread lock per file and lib.locks.file_lock hold the file from the read to the replace, so two subagents,
or two sessions' servers, that change one file take turns (D13). The write is one atomic replace (BYT-9).
Claude Code does not see an io tool's write as its own, so every result says to Read the file before the next
built-in Edit.
"""
import hashlib
import logging
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from ioguard.checks.journal_write import record_write
from ioguard.lib import locks, paths
from ioguard.lib.context import Context
from ioguard.lib.profile import BOM_CHAR, Bom, Profile, profile
from ioguard.lib.results import Code, Fix, Result, Severity, callable_name
from ioguard.mcp.toolspec import ToolFailure

NOTE = "The built-in Edit tool needs a fresh Read of this file before its next use."
LOCKS = paths.LockTable()
log = logging.getLogger("ioguard.mcp")


@dataclass(frozen=True)
class Place:
    first_line: int
    last_line: int

    def shown(self) -> str:
        if self.first_line == self.last_line:
            return f"{self.first_line:,}"
        return f"{self.first_line:,}-{self.last_line:,}"


def places_shown(places: list[Place]) -> str:
    """lines 3-5, 9, or line 4 for a single line."""
    single = len(places) == 1 and places[0].first_line == places[0].last_line
    return f"{'line' if single else 'lines'} {', '.join(place.shown() for place in places)}"


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


@dataclass(frozen=True)
class Written:
    data: bytes                      # the file's bytes after the call
    changed: bool

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    def profile_line(self) -> str:
        return profile(self.data).line()


def refused(code: Code, message: str, tool: str, path: Path, ctx: Context, fix: Fix | None = None,
            **evidence) -> ToolFailure:
    return ToolFailure(Result.of(code, message, tool, ctx.platform.os, severity=Severity.REFUSED, file=path,
                                 fix=fix, evidence=evidence))


def write_refused(path: Path, tool: str, ctx: Context, done: str) -> ToolFailure:
    """The refusal of a write the system refused: FILE_LOCKED naming the program that holds the file when
    the platform names one, else READ_ONLY, since the file or its folder cannot be written. done says what
    the call had written before, or that it wrote nothing."""
    try:
        holding = ", ".join(f"{each.name} (process {each.pid})" for each in ctx.fs.holders(path))
    except OSError:
        holding = ""
    if holding:
        return refused(Code.FILE_LOCKED, f"{holding} holds {path.name} open, so {tool} could not replace "
                       f"it.{done}", tool, path, ctx)
    return refused(Code.READ_ONLY, f"The system refused the write, and no program holds {path.name} open, "
                   f"so {tool} cannot write {path.name} or its folder.{done}", tool, path, ctx)


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
                stack.enter_context(locks.file_lock(path, locks.lock_folder(ctx.data_dir), wait_s))
            except TimeoutError:
                raise busy from None
            yield
    finally:
        lock.release()


def load(path: Path, ctx: Context, tool: str, expect_hash: str = "") -> Loaded:
    """The file's bytes and text, or the refusal that names why the tool cannot change it."""
    name = path.name
    device = paths.reserved(path) if ctx.platform.windows else None
    if device is not None:
        raise refused(Code.RESERVED_NAME, f"{name} names the Windows device {device.upper()}, which Windows "
                      f"tools cannot open or delete as a file, so {tool} wrote nothing.", tool, path, ctx,
                      Fix(callable_name(tool), {}, "Give the file another name."))
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


def encoded(loaded: Loaded, text: str, ctx: Context, tool: str) -> bytes:
    """text as the file's bytes, or the refusal that names a character the file's encoding cannot hold."""
    try:
        return loaded.encoded(text)
    except UnicodeEncodeError as error:
        character, codec = ord(error.object[error.start]), loaded.found.codec
        fix = Fix(callable_name(tool), {},
                  f"Use only characters {codec} holds, such as ASCII, in the new text.")
        raise refused(Code.ENCODING_INVALID, f"{loaded.path.name} is {codec}, which cannot hold "
                      f"U+{character:04X} from the new text, so {tool} wrote nothing.", tool, loaded.path,
                      ctx, fix) from None


def write(loaded: Loaded, data: bytes, ctx: Context, tool: str) -> Written:
    """data written over the file when it differs from what the file held. A program that holds the file
    open refuses the call, named when the platform can name it."""
    path = loaded.path
    if data != loaded.data:
        try:
            ctx.fs.write_atomic(path, data)
        except PermissionError:
            raise write_refused(path, tool, ctx, " It wrote nothing.") from None
        ctx.session.wrote(path)
        try:
            record_write(ctx, path, tool, loaded.data, data)
        except Exception:
            log.exception("GUARD_ERROR: io-guard could not add the %s of %s to the journal.", tool, path)
    return Written(data, data != loaded.data)
