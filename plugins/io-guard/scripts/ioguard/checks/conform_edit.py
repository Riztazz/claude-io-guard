"""Give an Edit's new text the indent of the lines around it.

When every indented line of new_string uses spaces and the lines around the one match of old_string use
tabs, or the other way round, the check converts new_string's indent. A new_string that mixes the two beside
lines that do not is a warning. A missing or repeated match, and replace_all, are left to the tool. The Edit
tool keeps a file's line endings, its BOM and the whitespace at the end of new_string, and matches old_string
against the file with its CRLF read as LF, so the check reads the file the same way.
"""
import re

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.profile import profile
from ioguard.lib.results import Code, Fix, Layer, Result, Severity

AROUND = 3                          # lines above and below the match that show the file's indent there
LEADING = re.compile(r"^[ \t]+", re.M)


def style(text: str) -> str:
    """How text's indented lines start: tabs, spaces, mixed, or none."""
    starts = [match[0] for match in LEADING.finditer(text) if match[0] != " "]
    tabs = any(start.startswith("\t") for start in starts)
    spaces = any(start.startswith("  ") for start in starts)
    return "mixed" if tabs and spaces else "tabs" if tabs else "spaces" if spaces else "none"


def reindented(text: str, to: str, width: int) -> str:
    """text with each line's leading tabs turned into width spaces, or its leading spaces into tabs."""
    def convert(match: re.Match) -> str:
        if to == "spaces":
            return match[0].replace("\t", " " * width)
        tabs, rest = divmod(len(match[0].expandtabs(width)), width)
        return "\t" * tabs + " " * rest
    return LEADING.sub(convert, text)


def space_step(text: str) -> int:
    """The smallest indent of text's space-indented lines, as the width one tab stands for."""
    sizes = [len(match[0]) for match in LEADING.finditer(text) if match[0].startswith("  ")]
    return min(sizes) if sizes else 4


class ConformEdit(Check):
    meta = CheckMeta(
        id="conform.edit", layer=Layer.BYTES, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.EDIT}), platforms=frozenset({"win32", "darwin"}), severity=Severity.FIXED,
        cost=Cost.MEDIUM, reads=frozenset({"file_path", "old_string", "new_string", "replace_all"}),
        writes=frozenset({"new_string"}), after=frozenset(), config={},
        codes=frozenset({Code.INDENT_MISMATCH}),
        description="Gives an Edit's new text the indent of the lines around it.")

    def run(self, event: Event, ctx: Context) -> Decision:
        path, old, new = event.file_path, event.old_string, event.new_string
        if path is None or old is None or new is None or event.replace_all or not old:
            return Decision.observe(self.meta.id)
        try:
            data = ctx.fs.read_bytes(path)
            text = data.decode("utf-8").removeprefix(chr(0xFEFF)).replace("\r\n", "\n")
        except (OSError, UnicodeDecodeError):
            return Decision.observe(self.meta.id)
        if text.count(old) != 1:
            return Decision.observe(self.meta.id)
        at = text.index(old)
        lines = text.split("\n")
        first = text.count("\n", 0, at)
        last = first + old.count("\n")
        around = "\n".join(lines[max(0, first - AROUND):last + AROUND + 1])
        here, given = style(around), style(new)
        if {here, given} == {"tabs", "spaces"}:
            width = profile(data).indent.width or space_step(around if here == "spaces" else new)
            converted = reindented(new, here, width)
            note = f"io-guard indented new_string with {here}, as the lines around the match are."
            rewrite = Rewrite(self.meta.id, frozenset({"new_string"}),
                              lambda given_input: {**given_input, "new_string": converted}, note,
                              Code.INDENT_MISMATCH)
            return Decision(self.meta.id, Verdict.ALLOW, rewrite=rewrite)
        if given == "mixed" and here in ("tabs", "spaces"):
            result = Result.of(Code.INDENT_MISMATCH,
                               f"new_string mixes tabs and spaces, and the lines around it use {here}.",
                               event.tool_name, ctx.platform.os, severity=Severity.WARNING, file=path,
                               fix=Fix("Edit", {}, f"Indent new_string with {here} only."))
            return Decision(self.meta.id, Verdict.ALLOW, results=(result,))
        return Decision.observe(self.meta.id)
