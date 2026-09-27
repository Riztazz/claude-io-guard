"""What a write changed in a file's bytes, against the file before it and the text the call asked for.

The caller decides what to report or repair. Lines are compared as text with the BOM removed and every line
ending read as LF, so a change of endings is one fact, from the two profiles, and never a change to every
line. The Edit tool matches old_string against the file read the same way.
"""
import difflib
import re
from dataclasses import dataclass

from ioguard.lib.profile import BOM_CHAR, LINE_BREAK, Bom, Eol, Profile, convert_eol, with_bom

STYLES = (Eol.CRLF, Eol.LF, Eol.CR)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
REPLACEMENT = re.compile(re.escape(chr(0xFFFD)))
NON_ASCII = re.compile(r"[^\x00-\x7f]")


@dataclass(frozen=True)
class Drift:
    eol: tuple[Eol, Eol] | None      # the ending style before and after, when a single style changed
    bom: tuple[Bom, Bom] | None      # the BOM before and after, when it changed
    nul: int                         # NUL bytes added
    control: int                     # other control bytes added
    replacement: int                 # U+FFFD characters added
    non_ascii: int                   # non-ASCII characters added
    invalid: bool                    # valid UTF-8 before, and not after
    size: tuple[int, int]            # bytes before and after


def drift(before: Profile, after: Profile) -> Drift:
    """How after differs from before in its endings, BOM, encoding and odd bytes. A file with no single
    ending style before, or with no line ending left after, has no ending change."""
    changed = before.eol in STYLES and after.eol not in (before.eol, Eol.NONE)
    eol = (before.eol, after.eol) if changed else None

    def added(name: str) -> int:
        return max(0, getattr(after.counts, name) - getattr(before.counts, name))

    return Drift(eol=eol, bom=None if before.bom is after.bom else (before.bom, after.bom), nul=added("nul"),
                 control=added("c0"), replacement=added("replacement"), non_ascii=added("non_ascii"),
                 invalid=before.encoding.utf8 and not after.encoding.utf8, size=(before.size, after.size))


def text_of(data: bytes) -> str:
    """The bytes as text for a line comparison: UTF-8, an undecodable byte as U+FFFD, and no BOM."""
    return data.decode("utf-8", "replace").removeprefix(BOM_CHAR)


def lines(text: str) -> list[str]:
    return LINE_BREAK.split(text.removeprefix(BOM_CHAR))


@dataclass(frozen=True)
class Edited:
    text: str                        # the whole file after the edit, every ending read as LF
    lines: frozenset[int]            # the lines of text, counted from 1, that new_string wrote


def edited(before: str, old: str, new: str, replace_all: bool) -> Edited | None:
    """before with the edit applied. None when old_string is not in before once, or at all for replace_all,
    because the tool then matched some other way or failed."""
    text, old, new = (LINE_BREAK.sub("\n", part) for part in (before.removeprefix(BOM_CHAR), old, new))
    found = text.count(old) if old else 0
    if found == 0 or (found > 1 and not replace_all):
        return None
    parts = text.split(old) if replace_all else text.split(old, 1)
    covered, line, spans = set(), 1, new.count("\n")
    for part in parts[:-1]:
        line += part.count("\n")
        covered.update(range(line, line + spans + 1))
        line += spans
    return Edited(new.join(parts), frozenset(covered))


def changed_lines(expected: str, actual: str) -> tuple[int, ...]:
    """The lines of actual, counted from 1, that differ from expected. A line removed shows as the line
    after it. The common head and tail are skipped before the diff, so one edit in a long file stays cheap."""
    want, got = lines(expected), lines(actual)
    head = 0
    while head < min(len(want), len(got)) and want[head] == got[head]:
        head += 1
    tail = 0
    while tail < min(len(want), len(got)) - head and want[-1 - tail] == got[-1 - tail]:
        tail += 1
    middle = difflib.SequenceMatcher(None, want[head:len(want) - tail], got[head:len(got) - tail],
                                     autojunk=False)
    found: set[int] = set()
    for tag, _, _, start, end in middle.get_opcodes():
        if tag != "equal":
            found.update(range(head + start + 1, head + max(end, start + 1) + 1))
    return tuple(sorted(line for line in found if line <= max(len(got), 1)))


def lines_holding(text: str, pattern: re.Pattern, among: tuple[int, ...] | None = None) -> tuple[int, ...]:
    """The lines of text, counted from 1, where pattern matches, only among the given lines when named."""
    wanted = None if among is None else frozenset(among)
    return tuple(number for number, line in enumerate(lines(text), 1)
                 if (wanted is None or number in wanted) and pattern.search(line))


def would_collapse(expected: int, actual: int, percent: int) -> bool:
    """True when actual bytes are under percent of the expected bytes."""
    return expected > 0 and actual * 100 < expected * percent


def restored(data: bytes, eol: Eol | None, bom: Bom) -> bytes | None:
    """data with its line endings written as eol, or left as they are for None, and its BOM as bom. None
    when data is not UTF-8."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return with_bom(text if eol is None else convert_eol(text, eol), bom).encode("utf-8")
