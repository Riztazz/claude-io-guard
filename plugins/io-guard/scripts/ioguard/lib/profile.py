"""A file's byte profile: its line endings, BOM, encoding, indent, shape and odd bytes, from its raw bytes.

Shell tools misreport a carriage return (BYT-5) and the Read tool hides endings and a BOM (BYT-4), so every
byte check compares a write against this profile, never against what a tool showed. The endings style comes
from the CRLF and LF counts, as the baseline survey counted them. A lone CR is counted and warned about, and
makes the style CR only when the file has no other ending. A UTF-16 file is counted in its UTF-8 form,
because its own NUL bytes are part of every character. Every count is a bytes method or a regex that starts
on a literal byte, so a megabyte profiles in a few milliseconds.
"""
import hashlib
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from ioguard.lib.text import BOM_CHAR, PRIVATE_USE

SNIFF_BYTES = 8 * 1024       # a NUL in this many leading bytes marks the file binary (INP-4)
C0 = bytes([*range(0x01, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20)])   # control bytes but tab, LF and CR
LEAD_BYTES = bytes(range(0xC0, 0x100))                              # each starts one UTF-8 character
HIGH_BYTES = bytes(range(0x80, 0x100))
REPLACEMENT = chr(0xFFFD).encode("utf-8")
PRIVATE_EF = re.compile(rb"\xef[\x80-\xa3]")      # U+F000 to U+F8FF, where U+E000 on starts with EE
SPACE_INDENT = re.compile(rb"\n( {2,})(?=[^\s])")
FIRST_SPACE_INDENT = re.compile(rb"( {2,})(?=[^\s])")
WIDTHS = (8, 4, 3, 2)
CENTRAL_EUROPEAN = frozenset(b"\x8c\x8f\x9c\x9f\xa3\xa5\xaa\xaf\xb3\xb9\xba\xbf")


class Eol(Enum):
    CRLF = "CRLF"
    LF = "LF"
    CR = "CR"
    MIXED = "mixed endings"
    NONE = "no endings"


class Bom(Enum):
    NONE = ""
    UTF8 = "BOM"
    UTF16_LE = "UTF-16 LE BOM"
    UTF16_BE = "UTF-16 BE BOM"


class IndentKind(Enum):
    TABS = "tabs"
    SPACES = "spaces"
    MIXED = "tabs and spaces"
    NONE = ""


@dataclass(frozen=True)
class EolCounts:
    crlf: int
    lf: int
    cr: int

    @property
    def dominant(self) -> Eol:
        """The ending most lines use, for a file that mixes them."""
        counts = {Eol.CRLF: self.crlf, Eol.LF: self.lf, Eol.CR: self.cr}
        best = max(counts, key=counts.get)
        return best if counts[best] else Eol.NONE


@dataclass(frozen=True)
class Encoding:
    utf8: bool
    first_invalid: int | None    # the byte offset of the first byte UTF-8 cannot decode
    guess: str | None            # "cp1250", "cp1252", "utf-16-le" or "utf-16-be" when not UTF-8


@dataclass(frozen=True)
class Indent:
    kind: IndentKind
    width: int | None            # the space step, for a file indented by spaces
    tab_lines: int
    space_lines: int


@dataclass(frozen=True)
class ByteCounts:
    nul: int
    c0: int                      # control bytes other than NUL, tab, LF and CR
    replacement: int             # U+FFFD, a character some tool already could not decode
    private_use: int             # glyphs that render as nothing in most fonts (ANC-5)
    non_ascii: int               # characters, not bytes
    trailing_ws_lines: int


@dataclass(frozen=True)
class Profile:
    eol: Eol
    eol_counts: EolCounts
    bom: Bom
    encoding: Encoding
    final_newline: bool
    line_count: int
    size: int
    indent: Indent
    counts: ByteCounts
    binary: bool
    sha256: str

    def line(self) -> str:
        """One line for the model, such as: CRLF, BOM, UTF-8, tabs, 1,284 lines."""
        if self.binary:
            return f"binary, {self.size:,} bytes"
        if self.encoding.utf8:
            encoding = "UTF-8"
        elif self.encoding.guess and self.encoding.guess.startswith("utf-16"):
            encoding = "UTF-16"
        else:
            encoding = f"not UTF-8, likely {self.encoding.guess}" if self.encoding.guess else "not UTF-8"
        indent = self.indent.kind.value
        if self.indent.kind is IndentKind.SPACES and self.indent.width:
            indent = f"{self.indent.width} spaces"
        lines = f"{self.line_count:,} line" + ("" if self.line_count == 1 else "s")
        return ", ".join(part for part in (self.eol.value, self.bom.value, encoding, indent, lines) if part)

    def warnings(self) -> tuple[str, ...]:
        """What about the bytes can go wrong in a write, each as one sentence."""
        found, counts = [], self.counts
        if self.eol is Eol.MIXED:
            found.append(f"The file mixes line endings: {self.eol_counts.crlf:,} CRLF and "
                         f"{self.eol_counts.lf:,} LF.")
        if self.eol_counts.cr and self.eol is not Eol.CR:
            found.append(f"The file holds {self.eol_counts.cr:,} lone CR that ends no line.")
        if not self.encoding.utf8 and self.encoding.first_invalid is not None:
            found.append(f"The file is not valid UTF-8 from byte {self.encoding.first_invalid:,}"
                         + (f", and reads as {self.encoding.guess}." if self.encoding.guess else "."))
        for count, what in ((counts.nul, "NUL bytes"), (counts.c0, "other control bytes"),
                            (counts.replacement, "U+FFFD replacement characters"),
                            (counts.private_use, "private-use glyphs, which most fonts show as nothing")):
            if count:
                found.append(f"The file holds {count:,} {what}.")
        return tuple(found)

    @property
    def codec(self) -> str:
        """The codec that reads the file's bytes whole, a BOM included as U+FEFF: UTF-8, UTF-16 by its BOM,
        or the code page the bytes suggest."""
        return "utf-8" if self.encoding.utf8 else self.encoding.guess or "utf-8"

    @property
    def new_eol(self) -> Eol:
        """The ending a new line takes: the file's own, the one most lines use in a file that mixes them, and
        LF in a file with no line ending yet."""
        if self.eol is Eol.MIXED:
            return self.eol_counts.dominant
        return Eol.LF if self.eol is Eol.NONE else self.eol


def bom_of(data: bytes) -> Bom:
    if data.startswith(b"\xef\xbb\xbf"):
        return Bom.UTF8
    if data.startswith(b"\xff\xfe"):
        return Bom.UTF16_LE
    if data.startswith(b"\xfe\xff"):
        return Bom.UTF16_BE
    return Bom.NONE


def eol_of(counts: EolCounts) -> Eol:
    if counts.crlf and counts.lf:
        return Eol.MIXED
    if counts.crlf or counts.lf:
        return Eol.CRLF if counts.crlf else Eol.LF
    return Eol.CR if counts.cr else Eol.NONE


def legacy_guess(data: bytes) -> str:
    """cp1250 when the high bytes read as Central European letters, cp1252 otherwise."""
    high = [byte for byte in data if byte > 0x7F]
    central = sum(byte in CENTRAL_EUROPEAN for byte in high)
    return "cp1250" if central and central * 3 >= len(high) else "cp1252"


def encoding_of(data: bytes, bom: Bom) -> tuple[Encoding, bytes]:
    """The encoding facts, and the bytes to count lines in: the file's own, or UTF-8 for a UTF-16 file."""
    if bom in (Bom.UTF16_LE, Bom.UTF16_BE):
        codec = "utf-16-le" if bom is Bom.UTF16_LE else "utf-16-be"
        return Encoding(False, None, codec), data[2:].decode(codec, "replace").encode("utf-8")
    body = data[3:] if bom is Bom.UTF8 else data
    try:
        body.decode("utf-8")
    except UnicodeDecodeError as error:
        return Encoding(False, error.start + len(data) - len(body), legacy_guess(body)), data
    return Encoding(True, None, None), data


def indent_of(layout: bytes) -> Indent:
    tab_lines = layout.count(b"\n\t") + layout.startswith(b"\t")
    first = FIRST_SPACE_INDENT.match(layout)
    widths = ([len(first[1])] if first else []) + [len(spaces) for spaces in SPACE_INDENT.findall(layout)]
    kind = (IndentKind.MIXED if tab_lines and widths else IndentKind.TABS if tab_lines
            else IndentKind.SPACES if widths else IndentKind.NONE)
    levels = Counter(widths)

    def fits(step: int) -> bool:
        """Most space-indented lines sit on a multiple of step."""
        return sum(count for size, count in levels.items() if size % step == 0) >= 0.8 * len(widths)

    width = (rise_step(layout) or next((step for step in WIDTHS if fits(step)), None)) if widths else None
    return Indent(kind, width, tab_lines, len(widths))


def rise_step(layout: bytes) -> int | None:
    """The space step a file indents by: the commonest rise, among WIDTHS, from one non-blank line to the
    next. A block rises by the step. A continuation line aligned under a bracket rises by whatever the bracket
    leaves, once per statement, so it is outvoted. The smaller step wins a tie. None with no such rise."""
    depths = [len(line) - len(line.lstrip(b" ")) for line in layout.split(b"\n")
              if line.strip() and not line.startswith(b"\t")]
    rises = Counter(after - before for before, after in zip(depths, depths[1:]) if after - before in WIDTHS)
    return min(rises, key=lambda step: (-rises[step], step)) if rises else None


def counts_of(layout: bytes, encoding: Encoding, bom: Bom) -> ByteCounts:
    """The odd bytes in the file's UTF-8 or legacy bytes. A legacy code page has no private-use glyph."""
    readable = encoding.utf8 or bom in (Bom.UTF16_LE, Bom.UTF16_BE)
    candidate = any(lead in layout for lead in (b"\xee", b"\xf3", b"\xf4")) or PRIVATE_EF.search(layout)
    private = len(PRIVATE_USE.findall(layout.decode("utf-8"))) if readable and candidate else 0
    if readable:
        non_ascii = len(layout) - len(layout.translate(None, LEAD_BYTES)) - (bom is Bom.UTF8)
    else:
        non_ascii = len(layout) - len(layout.translate(None, HIGH_BYTES))
    trailing = sum(layout.count(ending) for ending in (b" \n", b"\t\n", b" \r", b"\t\r"))
    return ByteCounts(nul=layout.count(b"\x00"), c0=len(layout) - len(layout.translate(None, C0)),
                      replacement=layout.count(REPLACEMENT), private_use=private, non_ascii=non_ascii,
                      trailing_ws_lines=trailing + layout.endswith((b" ", b"\t")))


def profile(data: bytes) -> Profile:
    """The profile of a file's bytes."""
    bom = bom_of(data)
    encoding, layout = encoding_of(data, bom)
    crlf = layout.count(b"\r\n")
    eol_counts = EolCounts(crlf, layout.count(b"\n") - crlf, layout.count(b"\r") - crlf)
    final_newline = layout.endswith((b"\n", b"\r"))
    body = layout[3:] if bom is Bom.UTF8 else layout
    line_count = eol_counts.crlf + eol_counts.lf + eol_counts.cr + (1 if body and not final_newline else 0)
    binary = bom not in (Bom.UTF16_LE, Bom.UTF16_BE) and b"\x00" in data[:SNIFF_BYTES]
    return Profile(eol=eol_of(eol_counts), eol_counts=eol_counts, bom=bom, encoding=encoding,
                   final_newline=final_newline, line_count=line_count, size=len(data), indent=indent_of(body),
                   counts=counts_of(layout, encoding, bom), binary=binary,
                   sha256=hashlib.sha256(data).hexdigest())


ENDINGS = {Eol.CRLF: "\r\n", Eol.LF: "\n", Eol.CR: "\r"}
LINE_BREAK = re.compile("\r\n|\r|\n")
ENDING = re.compile("\r\n|\n")
LONE_CR = re.compile("\r(?!\n)")


def convert_eol(text: str, eol: Eol) -> str:
    """text with every line ending, CRLF or LF, written as eol. A lone CR ends no line, so it stays as it is:
    converting it would split its line. A MIXED or NONE target leaves text as it is."""
    ending = ENDINGS.get(eol)
    return text if ending is None else ENDING.sub(lambda _: ending, text)


def lone_cr_lines(text: str) -> list[int]:
    """The line of each lone CR in text, counted from 1, where only CRLF and LF end a line."""
    return [text.count("\n", 0, found.start()) + 1 for found in LONE_CR.finditer(text)]


def with_bom(text: str, bom: Bom) -> str:
    """text that starts with a UTF-8 BOM when bom is UTF8, and without one otherwise. The Write tool writes
    a leading U+FEFF as the BOM's three bytes."""
    body = text.removeprefix(BOM_CHAR)
    return BOM_CHAR + body if bom is Bom.UTF8 else body


def with_final_newline(text: str, final: bool, eol: Eol) -> str:
    """text that ends with one line ending when final is true, and with none when it is false."""
    if final and text and not text.endswith(("\n", "\r")):
        return text + ENDINGS.get(eol, "\n")
    if not final:
        last = next((ending for ending in ("\r\n", "\n", "\r") if text.endswith(ending)), "")
        return text[:len(text) - len(last)]
    return text


def majority(values: Sequence, skip: tuple = ()) -> object | None:
    kept = [value for value in values if value not in skip]
    return Counter(kept).most_common(1)[0][0] if kept else None


def target_profile(siblings: Sequence[Profile], editorconfig: Mapping[str, str],
                   gitattributes: Mapping[str, str]) -> Profile:
    """The profile a new file takes: from the .editorconfig properties that apply to it first, then its
    .gitattributes, then the majority of its siblings with the same extension. Its counts are zero and its
    sha256 empty."""
    endings = {"crlf": Eol.CRLF, "lf": Eol.LF, "cr": Eol.CR}
    eol = (endings.get(editorconfig.get("end_of_line", "").lower())
           or endings.get(gitattributes.get("eol", "").lower())
           or majority([sibling.eol for sibling in siblings], (Eol.MIXED, Eol.NONE)) or Eol.NONE)
    charsets = {"utf-8-bom": Bom.UTF8, "utf-8": Bom.NONE, "utf-16le": Bom.UTF16_LE, "utf-16be": Bom.UTF16_BE}
    bom = charsets.get(editorconfig.get("charset", "").lower())
    if bom is None:
        bom = majority([sibling.bom for sibling in siblings]) or Bom.NONE
    style = editorconfig.get("indent_style", "").lower()
    if style in ("tab", "space"):
        size = editorconfig.get("indent_size", "")
        indent = Indent(IndentKind.TABS if style == "tab" else IndentKind.SPACES,
                        int(size) if style == "space" and size.isascii() and size.isdigit() else None, 0, 0)
    else:
        kind = majority([sibling.indent.kind for sibling in siblings], (IndentKind.NONE,)) or IndentKind.NONE
        width = majority([sibling.indent.width for sibling in siblings if sibling.indent.kind is kind],
                         (None,))
        indent = Indent(kind, width if kind is IndentKind.SPACES else None, 0, 0)
    final = editorconfig.get("insert_final_newline", "").lower()
    final_newline = (final == "true" if final in ("true", "false")
                     else majority([sibling.final_newline for sibling in siblings]) is not False)
    utf16 = bom in (Bom.UTF16_LE, Bom.UTF16_BE)
    codec = ("utf-16-le" if bom is Bom.UTF16_LE else "utf-16-be") if utf16 else None
    return Profile(eol=eol, eol_counts=EolCounts(0, 0, 0), bom=bom, encoding=Encoding(not utf16, None, codec),
                   final_newline=final_newline, line_count=0, size=0, indent=indent,
                   counts=ByteCounts(0, 0, 0, 0, 0, 0), binary=False, sha256="")
