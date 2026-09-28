"""Changes to a file's text, placed the way the Edit tool reads the file and made in the file's own text.

The Edit tool reads every line ending as LF, so a place is found and counted in that view of the text. The
change then lands in the text as the file holds it: every character outside the change keeps its ending,
whatever mix of endings the file has, each line break in the new text takes the one ending the caller names,
and new text indented with tabs beside lines indented with spaces, or the other way round, takes their style.
Appended lines go after the last one, and a long line wraps with its continuation under its first word.
"""
import bisect
import re
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass

from ioguard.lib import anchors, indent
from ioguard.lib.profile import Eol, convert_eol

CRLF = re.compile("\r\n")
LIST_LEAD = re.compile(r"[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?")


@dataclass(frozen=True)
class Change:
    old: str                         # found exactly once, with every line ending read as LF
    new: str


@dataclass(frozen=True)
class Changed:
    text: str
    start: int                       # where the new text sits in text's LF view
    end: int
    indented: str | None             # "tabs" or "spaces" when the new text took the indent around it


@dataclass(frozen=True)
class Missed:
    index: int                       # the change whose old text is not in the text once, counted from 0
    text: str                        # the text it was looked for in, after the changes before it
    matches: tuple[anchors.Match, ...]


@dataclass(frozen=True)
class Applied:
    text: str
    lines: tuple[tuple[int, int], ...]       # each change's first and last line in text, counted from 1
    indented: tuple[tuple[int, str], ...]    # each change, from 0, whose new text took the indent around it


def replaced(text: str, start: int, end: int, new: str, eol: Eol) -> str:
    """text with start:end of its LF view replaced by new, each line break in new written as eol. Each CRLF
    before a view offset moves that offset one character further into text."""
    collapsed = [match.start() - number for number, match in enumerate(CRLF.finditer(text))]

    def at(offset: int) -> int:
        return offset + bisect.bisect_left(collapsed, offset)
    return text[:at(start)] + convert_eol(new, eol) + text[at(end):]


def change(text: str, start: int, end: int, new: str, eol: Eol, width: int | None) -> Changed:
    """text with start:end of its LF view replaced by new, in the indent of the lines around it. width is the
    file's space step, or None when the file has none."""
    view = anchors.edit_view(text)
    first = anchors.line_of(view, start)
    near = indent.around(view, first, anchors.line_of(view, max(start, end - 1)))
    fitted = indent.fitted(new, near, width)
    placed = new if fitted is None else fitted
    return Changed(replaced(text, start, end, placed, eol), start, start + len(anchors.edit_view(placed)),
                   None if fitted is None else indent.style(near))


def apply(text: str, changes: Sequence[Change], eol: Eol, width: int | None) -> Applied | Missed:
    """text with each change made in order, each old text found exactly once in what the changes before it
    left. Missed names the first change that is not, and then no change is made."""
    spans: list[tuple[int, int]] = []
    indented: list[tuple[int, str]] = []
    for index, wanted in enumerate(changes):
        found = anchors.find(anchors.edit_view(text), anchors.edit_view(wanted.old))
        if len(found) != 1:
            return Missed(index, text, found)
        start, end = found[0].start, found[0].end
        made = change(text, start, end, wanted.new, eol, width)
        shift = (made.end - made.start) - (end - start)
        spans = [(first + shift, last + shift) if first >= end else (first, last) if last <= start
                 else (min(first, start), max(last, end) + shift) for first, last in spans]
        spans.append((made.start, made.end))
        if made.indented is not None:
            indented.append((index, made.indented))
        text = made.text
    view = anchors.edit_view(text)
    lines = tuple((anchors.line_of(view, first), anchors.line_of(view, max(first, last - 1)))
                  for first, last in spans)
    return Applied(text, lines, tuple(indented))


def appended(text: str, addition: str, eol: Eol) -> str:
    """text with addition as new lines at its end, each line break written as eol. A last line with no
    ending gets one first, and then the addition ends with none, as the file did."""
    added = convert_eol(addition.rstrip("\r\n"), eol)
    ending = convert_eol("\n", eol)
    if text and not text.endswith(("\n", "\r")):
        return text + ending + added
    return text + added + ending


def wrapped(text: str, column: int) -> str:
    """text with each line longer than column broken at spaces. The lines after the first start where the
    first line's words do, past its indent and any list marker. A word longer than column stays whole."""
    out: list[str] = []
    for line in anchors.edit_view(text).split("\n"):
        if len(line) <= column:
            out.append(line)
            continue
        lead = LIST_LEAD.match(line)[0]
        out += textwrap.wrap(line, column, subsequent_indent=re.sub(r"[^ \t]", " ", lead),
                             break_long_words=False, break_on_hyphens=False, expand_tabs=False,
                             replace_whitespace=False)
    return "\n".join(out)
