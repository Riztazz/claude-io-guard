"""How lines are indented, and new text given the indent of the lines where it lands.

One file indents with tabs and the next with spaces, often inside one repository (BYT-11), so new text takes
the style of the few lines around its place in the file rather than a project-wide rule.
"""
import re

from ioguard.lib.profile import IndentKind

AROUND = 3                          # lines above and below a place that show the file's indent there
LEADING = re.compile(r"^[ \t]+", re.M)
BOTH = {IndentKind.TABS, IndentKind.SPACES}


def style(text: str) -> IndentKind:
    """How text's indented lines start: tabs, spaces, both, or none."""
    starts = [match[0] for match in LEADING.finditer(text) if match[0] != " "]
    tabs = any(start.startswith("\t") for start in starts)
    spaces = any(start.startswith("  ") for start in starts)
    if tabs and spaces:
        return IndentKind.MIXED
    return IndentKind.TABS if tabs else IndentKind.SPACES if spaces else IndentKind.NONE


def reindented(text: str, to: IndentKind, width: int) -> str:
    """text with each line's leading tabs turned into width spaces, for SPACES, or its leading spaces into
    tabs, for TABS."""
    def convert(match: re.Match) -> str:
        if to is IndentKind.SPACES:
            return match[0].replace("\t", " " * width)
        tabs, rest = divmod(len(match[0].expandtabs(width)), width)
        return "\t" * tabs + " " * rest
    return LEADING.sub(convert, text)


def space_step(text: str) -> int:
    """The smallest indent of text's space-indented lines, as the width one tab stands for."""
    sizes = [len(match[0]) for match in LEADING.finditer(text) if match[0].startswith("  ")]
    return min(sizes) if sizes else 4


def around(text: str, first: int, last: int) -> str:
    """The lines of LF text from AROUND lines above line first to AROUND lines below line last, counted
    from 1."""
    return "\n".join(text.split("\n")[max(0, first - 1 - AROUND):last + AROUND])


def fitted(new: str, near: str, width: int | None) -> str | None:
    """new in the indent style of near, when one indents with tabs and the other with spaces. None when the
    two agree, or when either mixes the styles or has no indent. width is the file's space step, or None to
    take the step from whichever side uses spaces."""
    here, given = style(near), style(new)
    if {here, given} != BOTH:
        return None
    return reindented(new, here, width or space_step(near if here is IndentKind.SPACES else new))
