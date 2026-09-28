"""io.read: a file's lines exactly as the file holds them, after its profile: endings, BOM, encoding, indent.

The built-in Read shows a CRLF file, an LF file and a file with a BOM the same way (BYT-4), and refuses some
text files as binary (INP-4). io.read decides text or binary from the bytes, and its structured result keeps
every CR and BOM in the text, where the model sees them. The text copy marks them as [CR] and [BOM]. An
io.read does not count as a Read for the built-in Edit, because Claude Code tracks only its own tools' reads
(D3), and the result says so.
"""
import re
from dataclasses import dataclass

from ioguard.lib import paths, text
from ioguard.lib.profile import Bom, Profile, profile
from ioguard.lib.results import Code, Fix, Result
from ioguard.mcp.toolspec import ToolCall, ToolFailure, ToolSpec, callable_name, doc

NAME = "io.read"
LINE = re.compile(r"[^\n]*\n|[^\n]+")
HEAD_BYTES = 64
NOTE = "io.read is not a Read for the built-in Edit tool, so Read the file before you Edit it."


@dataclass(frozen=True)
class ReadInput:
    path: str = doc("The file, absolute or from the project folder.")
    offset: int = doc("The first line to return, counted from 1.", default=1)
    limit: int = doc("The most lines to return.", default=2000)


@dataclass(frozen=True)
class ReadOutput:
    path: str = doc("The file, as a path with forward slashes.")
    profile: str = doc("Endings, BOM, encoding, indent and lines, such as CRLF, BOM, UTF-8, tabs, 12 lines.")
    binary: bool = doc("The bytes are not text, so text is empty and head_hex holds the first bytes.")
    size: int = doc("The file's size in bytes.")
    first_line: int = doc("The first line returned, counted from 1. 0 when none was.")
    last_line: int = doc("The last line returned.")
    total_lines: int = doc("The lines in the file.")
    text: str = doc("The lines, each with its own ending, and a BOM as U+FEFF at the start of line 1.")
    head_hex: str = doc("The first bytes of a binary file, in hex.")
    next: str = doc("The call for the lines after these, or empty when none are left.")
    note: str = doc("What this read does not do.")

    def render(self) -> str:
        if self.binary:
            return f"{self.path}: binary, {self.size:,} bytes. First bytes: {self.head_hex}\n{self.note}"
        lines = f"lines {self.first_line:,}-{self.last_line:,}" if self.first_line else "no lines"
        body = text.snippet(self.text, 1, self.last_line - self.first_line + 1, 0) if self.text else ""
        numbered = "\n".join(renumbered(body, self.first_line - 1))
        header = f"{self.path}: {self.profile}, {lines} of {self.total_lines:,}"
        parts = [header, numbered, self.next, self.note]
        return "\n".join(part for part in parts if part)


def renumbered(snippet: str, shift: int) -> list[str]:
    """snippet's lines numbered from the file's own first line rather than from 1."""
    out = []
    for line in snippet.split("\n"):
        number, _, rest = line.partition("| ")
        if number.strip().isdigit():
            out.append(f"{int(number) + shift:>6}| {rest}")
    return out


def decoded(data: bytes, found: Profile) -> str:
    """The file's text, its BOM kept as U+FEFF. A file that is not UTF-8 decodes in the code page its bytes
    suggest."""
    if found.bom is Bom.UTF16_LE:
        return data.decode("utf-16-le", "replace")
    if found.bom is Bom.UTF16_BE:
        return data.decode("utf-16-be", "replace")
    if found.encoding.utf8:
        return data.decode("utf-8")
    return data.decode(found.encoding.guess or "utf-8", "replace")


def read(given: ReadInput, call: ToolCall) -> ReadOutput:
    ctx = call.context
    path = paths.normalise(given.path, call.cwd, ctx.platform)
    shown = path.as_posix()
    glob = Fix("Glob", {"pattern": f"**/{path.name}"}, f"Glob for **/{path.name} to find where it is.")
    found = ctx.fs.stat(path)
    if found is None:
        raise ToolFailure(Result.of(Code.PATH_NOT_FOUND, f"{shown} does not exist.", NAME, ctx.platform.os,
                                    file=path, fix=glob))
    limit = ctx.config.get("io.read.max_bytes")
    if found.size > limit:
        raise ToolFailure(Result.of(Code.READ_TOO_LARGE, f"{shown} holds {found.size:,} bytes, more than "
                                    f"io.read reads, {limit:,}.", NAME, ctx.platform.os, file=path,
                                    fix=Fix("Read", {"file_path": str(path)},
                                            "Read it in parts with the Read tool's offset and limit.")))
    try:
        data = ctx.fs.read_bytes(path)
    except OSError as error:
        raise ToolFailure(Result.of(Code.PATH_NOT_FOUND, f"{shown} cannot be read as a file: "
                                    f"{error.strerror or error}.", NAME, ctx.platform.os, file=path,
                                    fix=glob)) from None
    found_profile = profile(data)
    if found_profile.binary:
        return ReadOutput(shown, found_profile.line(), True, len(data), 0, 0, 0, "",
                          data[:HEAD_BYTES].hex(" "), "", NOTE)
    lines = LINE.findall(decoded(data, found_profile))
    first = max(1, given.offset)
    budget, taken = ctx.config.get("io.read.max_chars"), []
    for line in lines[first - 1:first - 1 + max(0, given.limit)]:
        if taken and sum(map(len, taken)) + len(line) > budget:
            break
        taken.append(line)
    last = first + len(taken) - 1
    after = f"Call {callable_name(NAME)} with offset {last + 1} for the rest." if last < len(lines) else ""
    return ReadOutput(shown, found_profile.line(), False, len(data), first if taken else 0,
                      last if taken else 0, len(lines), "".join(taken), "", after, NOTE)


SPECS = (ToolSpec(NAME, "Read a file byte for byte",
                  "Reads a file's lines exactly as the file holds them, and names its line endings, BOM, "
                  "encoding and indent, which the built-in Read hides. Use it to see CRLF, a BOM, tabs or a "
                  "text file the Read tool calls binary.",
                  ReadInput, ReadOutput, read_only=True, destructive=False, idempotent=True, handler=read),)
