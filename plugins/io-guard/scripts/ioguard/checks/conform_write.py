"""Write new content in the file's own line endings, BOM and final newline, before the Write tool runs.

The Write tool writes LF over a CRLF file and drops a BOM (BYT-1, BYT-7), and git then marks every line
changed. For a file that exists, the content takes that file's line ending, BOM and final-newline convention.
A file that mixes endings keeps the content's endings, with a warning, because no one ending is its own. A new
file takes the convention target_profile gives: the .editorconfig properties that apply to it, then its
.gitattributes, then most of the files with its extension in the nearest folder at or above its own that holds
any, up to its repository's root, and the note names that folder when it is not the file's own. With none of
those, the content stays as written. A lone CR in the content ends no line, so it stays as written, and the
agent hears which line holds it, since the Read tool shows it as nothing. A binary or UTF-16 file is left
alone, because the Write tool writes UTF-8 text. hooks.answer leaves the permission decision to the harness,
which asks or approves as it would have for the original call.
"""
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import editorconfig, paths
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.folders import repository_root
from ioguard.lib.git import GitError
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.profile import (Bom, Eol, Profile, convert_eol, lone_cr_lines, profile, target_profile,
                                 with_bom, with_final_newline)
from ioguard.lib.results import Code, Fix, Layer, Result, Severity
from ioguard.lib.text import BOM_CHAR

SIBLINGS = 20                  # the most same-extension files profiled for a new file's convention
SIBLING_BYTES = 64 * 1024      # read from each, enough for its endings, BOM and indent
EDITORCONFIG_KEYS = ("end_of_line", "charset", "insert_final_newline")


def read_text(ctx: Context, path: Path) -> str | None:
    try:
        return ctx.fs.read_bytes(path).decode("utf-8", "replace")
    except OSError:
        return None


def like_files_in(folder: Path, path: Path, ctx: Context) -> list[Profile]:
    """The profiles of the text files in folder with path's extension, path itself left out."""
    found = []
    for sibling in ctx.fs.list_dir(folder):
        if sibling != path and sibling.suffix.lower() == path.suffix.lower() and len(found) < SIBLINGS:
            try:
                found.append(profile(ctx.fs.read_bytes(sibling, SIBLING_BYTES)))
            except OSError:
                continue
    return [sibling for sibling in found if not sibling.binary]


def like_files(path: Path, ctx: Context) -> tuple[list[Profile], Path]:
    """The files with path's extension in the nearest folder at or above path's own that holds any, up to its
    repository's root, and that folder. A folder the same call creates holds none yet. Outside a repository
    only path's own folder is read."""
    found = like_files_in(path.parent, path, ctx)
    existing = next((folder for folder in path.parents if ctx.fs.is_dir(folder)), None)
    top = None if found or existing is None else repository_root(ctx.git, existing)
    if top is None or not path.parent.is_relative_to(top):
        return found, path.parent
    for folder in (folder for folder in path.parent.parents if folder.is_relative_to(top)):
        if above := like_files_in(folder, path, ctx):
            return above, folder
    return [], path.parent


def new_file_target(path: Path, ctx: Context) -> tuple[Profile | None, Path]:
    """The convention a new file takes, or None when nothing names one, and the folder whose files set it."""
    properties = editorconfig.properties(path, lambda file: read_text(ctx, file))
    try:
        attributes = dict(ctx.git.attributes(path))
    except GitError:
        attributes = {}
    siblings, folder = like_files(path, ctx)
    if not siblings and "eol" not in attributes and not any(key in properties for key in EDITORCONFIG_KEYS):
        return None, folder
    return target_profile(siblings, properties, attributes), folder


def conformed(content: str, target: Profile, existing: bool) -> str:
    """content in target's endings, BOM and final newline. A new file's content keeps a BOM it was given,
    and a file with no line ending yet takes no final-newline rule."""
    text = convert_eol(content, target.eol)
    if target.eol is not Eol.NONE:
        text = with_final_newline(text, target.final_newline, target.eol)
    if existing or target.bom is Bom.UTF8:
        text = with_bom(text, target.bom)
    return text


class ConformWrite(Check):
    meta = CheckMeta(
        id="conform.write", layer=Layer.BYTES, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.WRITE}), platforms=EVERY_PLATFORM, severity=Severity.FIXED,
        cost=Cost.EXPENSIVE, reads=frozenset({"file_path", "content"}), writes=frozenset({"content"}),
        after=frozenset(), config={},
        codes=frozenset({Code.EOL_CONVERTED, Code.BOM_RESTORED, Code.EOL_MISMATCH}),
        description="Writes new content in the file's own line endings, BOM and final newline.")

    def run(self, event: Event, ctx: Context) -> Decision:
        path, content = event.file_path, event.content
        if path is None or content is None:
            return Decision.observe(self.meta.id)
        try:
            found = profile(ctx.fs.read_bytes(path))
        except OSError:
            found = None
        existing = found is not None and found.size > 0
        if existing and (found.binary or found.bom in (Bom.UTF16_LE, Bom.UTF16_BE)):
            return Decision.observe(self.meta.id)
        if existing and found.eol is Eol.MIXED:
            result = Result.of(Code.EOL_MISMATCH,
                               f"{path.name} mixes line endings, {found.eol_counts.crlf:,} CRLF and "
                               f"{found.eol_counts.lf:,} LF, so io-guard left the new content's endings as "
                               f"written.", event.tool_name, ctx.platform.os, file=path,
                               fix=Fix("Write", {}, "Write the whole file in one ending."))
            return Decision(self.meta.id, Verdict.ALLOW, results=(result,))
        target, folder = (found, path.parent) if existing else new_file_target(path, ctx)
        if target is None:
            return Decision.observe(self.meta.id)
        text = conformed(content, target, existing)
        kept = self.lone_crs(content, target, path, event, ctx)
        if text == content and not kept:
            return Decision.observe(self.meta.id)
        if text == content:
            return Decision(self.meta.id, Verdict.ALLOW, results=kept)
        endings_changed = text.removeprefix(BOM_CHAR) != content.removeprefix(BOM_CHAR)
        code = Code.EOL_CONVERTED if endings_changed else Code.BOM_RESTORED
        if existing:
            whose = f"{path.name} has them"
        elif folder == path.parent:
            whose = f"a new {path.suffix or 'file'} here takes them"
        else:
            whose = f"the {path.suffix} files in {paths.shown(folder, event.cwd)} have them"
        note = (f"io-guard wrote the content with {target.eol.value} line endings"
                + (", a BOM" if target.bom is Bom.UTF8 else "")
                + (", and a final newline" if target.final_newline and target.eol is not Eol.NONE else "")
                + f", as {whose}.")
        return Decision(self.meta.id, Verdict.ALLOW, results=kept,
                        rewrite=Rewrite(self.meta.id, frozenset({"content"}),
                                        lambda given: {**given, "content": text}, note, code))

    @staticmethod
    def lone_crs(content: str, target: Profile, path: Path, event: Event, ctx: Context) -> tuple[Result, ...]:
        """EOL_MISMATCH naming each line of the content that holds a lone CR, which the Read tool shows as
        nothing. In a CR file a CR is the file's own ending, so nothing is named."""
        lines = [] if target.eol is Eol.CR else lone_cr_lines(content)
        if not lines:
            return ()
        where = ", ".join(f"{line:,}" for line in lines[:5]) + (f" and {len(lines) - 5:,} more"
                                                                   if len(lines) > 5 else "")
        message = (f"The content holds a lone CR, which ends no line, on line {where}, and io-guard kept it "
                   f"as written.")
        fix = Fix("Write", {}, "Take it out if the line was meant to end or to run on, since the Read tool "
                               "shows it as nothing.")
        return (Result.of(Code.EOL_MISMATCH, message, event.tool_name, ctx.platform.os, file=path,
                          severity=Severity.WARNING, fix=fix, evidence={"lines": lines}),)
