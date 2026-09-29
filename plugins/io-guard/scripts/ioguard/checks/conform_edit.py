"""Give an Edit's new text the indent of the lines around it, and stop one that joins two words or two lines.

When every indented line of new_string uses spaces and the lines around the one match of old_string use
tabs, or the other way round, the check converts new_string's indent. A new_string that mixes the two beside
lines that do not is a warning. The indent of a missing or repeated match, or of replace_all, is left alone.
The Edit tool keeps a file's line endings, its BOM and the whitespace at the end of new_string, and matches
old_string against the file with every ending read as LF, so the check reads the file the same way.

A space or tab at the end of new_string is gone from the model's own call before any hook sees it (context.md,
"Hooks and MCP", row 28). So an old_string that ends in one, beside a new_string that ends in none, joins
new_string to the text after the match wherever the line goes on: .Branch, 1 becomes .Branch.ToInt(),1. The
check refuses that Edit, with the joined lines and the strings that end one character later. Those carry the
model's intent either way, since the space inside them survives: .Branch, 1 to .Branch.ToInt(), 1 keeps it,
and .Branch, 1 to .Branch.ToInt(),1 drops it.

An Edit with an empty new_string also loses the line break after its match (context.md, "Hooks and MCP", row
41). So a deletion whose old_string opens with a line break, and ends on one, its own or that one, joins the
line before it to the line after. The check refuses it when both lines hold text, with the same lines'
old_string moved one line break later, which deletes them and joins nothing.
"""
import json

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import anchors, indent
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.profile import profile
from ioguard.lib.results import Code, Fix, Layer, Result, Severity
from ioguard.lib.text import SHOWN, listed


class ConformEdit(Check):
    meta = CheckMeta(
        id="conform.edit", layer=Layer.BYTES, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.EDIT}), platforms=frozenset({"win32", "darwin"}), severity=Severity.FIXED,
        cost=Cost.MEDIUM, reads=frozenset({"file_path", "old_string", "new_string", "replace_all"}),
        writes=frozenset({"new_string"}), after=frozenset(),
        config={
            "space_dropped": ConfigKey(bool, True, "Refuse an Edit whose old_string ends in a space or tab "
                                       "that new_string lacks, where the line goes on after it."),
            "lines_joined": ConfigKey(bool, True, "Refuse a deletion whose old_string opens with a line "
                                      "break and ends without one, where a line break follows it."),
        },
        codes=frozenset({Code.INDENT_MISMATCH, Code.SPACE_DROPPED, Code.LINES_JOINED}),
        description="Gives an Edit's new text the indent of the lines around it, and stops one that joins "
                    "two words or two lines.")

    def run(self, event: Event, ctx: Context) -> Decision:
        path, old, new = event.file_path, event.old_string, event.new_string
        if path is None or old is None or new is None or not old:
            return Decision.observe(self.meta.id)
        try:
            data = ctx.fs.read_bytes(path)
            text = anchors.edit_view(data.decode("utf-8").removeprefix(chr(0xFEFF)))
        except (OSError, UnicodeDecodeError):
            return Decision.observe(self.meta.id)
        every = event.replace_all is True
        joined = anchors.joins(text, old, new, every) if self.options["space_dropped"] else ()
        if joined:
            return Decision(self.meta.id, Verdict.DENY, results=(dropped(joined, old, new, event, ctx),))
        merged = anchors.deletion_joins(text, old, new, every) if self.options["lines_joined"] else ()
        if merged:
            return Decision(self.meta.id, Verdict.DENY, results=(lines_merged(merged, old, event, ctx),))
        if every or text.count(old) != 1:
            return Decision.observe(self.meta.id)
        first = anchors.line_of(text, text.index(old))
        near = indent.around(text, first, first + old.count("\n"))
        here = indent.style(near)
        converted = indent.fitted(new, near, profile(data).indent.width)
        if converted is not None:
            note = f"io-guard indented new_string with {here}, as the lines around the match are."
            rewrite = Rewrite(self.meta.id, frozenset({"new_string"}),
                              lambda given_input: {**given_input, "new_string": converted}, note,
                              Code.INDENT_MISMATCH)
            return Decision(self.meta.id, Verdict.ALLOW, rewrite=rewrite)
        if indent.style(new) == "mixed" and here in ("tabs", "spaces"):
            result = Result.of(Code.INDENT_MISMATCH,
                               f"new_string mixes tabs and spaces, and the lines around it use {here}.",
                               event.tool_name, ctx.platform.os, severity=Severity.WARNING, file=path,
                               fix=Fix("Edit", {}, f"Indent new_string with {here} only."))
            return Decision(self.meta.id, Verdict.ALLOW, results=(result,))
        return Decision.observe(self.meta.id)


def lines_merged(merged: tuple[anchors.Joined, ...], old: str, event: Event, ctx: Context) -> Result:
    """The refusal: each line as the deletion would leave it, and old_string moved one line break later."""
    shown = "\n".join(f"{place.line}| {place.after}" for place in merged[:SHOWN])
    message = (f"This Edit deletes old_string and the line break after it, so it joins the lines on "
               f"{listed(tuple(place.line for place in merged))} of {event.file_path.name}:\n{shown}")
    moved = old[1:] if old.endswith("\n") else old[1:] + "\n"
    join = "To join them on purpose, send both lines as old_string and the joined line as new_string."
    if not moved:
        return Result.of(Code.LINES_JOINED, message, event.tool_name, ctx.platform.os, file=event.file_path,
                         evidence={"lines": [place.line for place in merged]}, fix=Fix("Edit", {}, join))
    text = (f"Send exactly old_string {json.dumps(moved)} and an empty new_string, with no line break before "
            f"it, so the same lines go and the lines around them stay apart. {join}")
    return Result.of(Code.LINES_JOINED, message, event.tool_name, ctx.platform.os, file=event.file_path,
                     evidence={"lines": [place.line for place in merged]},
                     fix=Fix("Edit", {"old_string": moved, "new_string": ""}, text))


def dropped(joined: tuple[anchors.Joined, ...], old: str, new: str, event: Event, ctx: Context) -> Result:
    """The refusal: the lines as the Edit would leave them, and the strings that end one character later."""
    space = old[len(old.rstrip(" \t")):]
    what = "a space" if space == " " else "a tab" if space == "\t" else "spaces or tabs"
    name, first = event.file_path.name, joined[0]
    shown = "\n".join(f"{place.line}| {place.after}" for place in joined[:SHOWN])
    message = (f"This Edit joins the text on {listed(tuple(place.line for place in joined))} of {name}, "
               f"because old_string ends in {what} and new_string arrived without it:\n{shown}")
    followers = {place.next for place in joined}
    each = "" if len(followers) == 1 else " Make one Edit for each character that follows."
    keep = {"old_string": old + first.next, "new_string": new + space + first.next}
    text = (f"A trailing space in new_string never reaches the Edit tool, so end both strings one character "
            f"later, as old_string {json.dumps(keep['old_string'])} and new_string "
            f"{json.dumps(keep['new_string'])} to keep the space.{each}")
    return Result.of(Code.SPACE_DROPPED, message, event.tool_name, ctx.platform.os, file=event.file_path,
                     evidence={"lines": [place.line for place in joined]}, fix=Fix("Edit", keep, text))
