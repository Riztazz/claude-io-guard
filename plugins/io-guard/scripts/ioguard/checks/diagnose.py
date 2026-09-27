"""Answer a failed file call with where the text really is, the paths that exist, or the parts that fit.

Two routes reach one diagnosis. A Read, Grep or Glob that fails while it runs fires PostToolUseFailure, and
diagnose.failure answers there. An Edit or Write that Claude Code rejects before it runs fires no hook at all
(context.md, "Hooks and MCP", row 30), so diagnose.refused finds the refusal at the end of the transcript at
the session's next hook, and answers once per refused call, before the model tries again.

An old_string that is not in the file gets the lines it matches once spaces and tabs are ignored, with the
corrected old_string, or else the lines most like it, numbered and with tabs and trailing spaces marked. One
found more than once gets each place and the shortest old_string that names the first. An Edit with the same
old_string and new_string, and a call refused because the file changed after the Read, get the lines the call
aimed at as they are now. A missing file gets the files of the same name nearby: from git in a repository,
otherwise from a bounded walk of the nearest folder that exists. A missing search folder gets the nearest
folder that exists. A Read past the limit gets parts that fit, a pattern ripgrep rejects gets its reason and a
literal pattern, and a search that timed out gets narrowed. A lock is write.locks' to name.
"""
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import anchors, paths, text, transcript
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.git import GitError
from ioguard.lib.profile import profile
from ioguard.lib.results import Code, Fix, Layer, Result, Severity

MISSING = re.compile(r"^(?:File|Path|Directory) does not exist")
TOO_LARGE = re.compile(r"exceeds maximum allowed (?:size|tokens)")
PATTERN = re.compile(r"ripgrep rejected the pattern")
TIMED_OUT = re.compile(r"timed out after (\d+) seconds")
AMBIGUOUS = re.compile(r"^Found \d+ matches of the string to replace")
NOT_FOUND = "String to replace not found"
IDENTICAL = "No changes to make: old_string and new_string are exactly the same"
CHANGED = "has been modified since read"
LOOK_AROUND = re.compile(r"look-around|backreference", re.I)
RG_META = re.compile(r"([\\.+*?()|\[\]{}^$])")
SHOWN = 5                    # places or paths a message lists
CORRECTION_CHARS = 1_500     # the longest corrected old_string a message quotes in full
TAIL_BYTES = 256 * 1024
FIND_LIMIT = 20_000
PART_BYTES = 60_000
MARKED = "Copy old_string from those lines, with [TAB] as a tab and [SP] as a space, and call Edit again."


@dataclass(frozen=True)
class Failed:
    tool: str
    tool_input: Mapping[str, Any]
    error: str
    cwd: Path


def file_text(data: bytes) -> str:
    """The file as the Edit tool reads it: UTF-8, every line ending as LF, no BOM."""
    decoded = data.decode("utf-8", "replace").removeprefix(chr(0xFEFF))
    return decoded.replace("\r\n", "\n").replace("\r", "\n")


def span(match: anchors.Match) -> str:
    first, last = match.first_line, match.last_line
    return f"line {first:,}" if first == last else f"lines {first:,}-{last:,}"


def shown(path: Path, cwd: Path) -> str:
    """path from cwd when it is under cwd, whole otherwise."""
    try:
        relative = path.relative_to(cwd).as_posix()
    except ValueError:
        return path.as_posix()
    return "the current folder" if relative == "." else relative


def quoted(value: str, instead: str) -> str:
    """value as a JSON string the model can copy exactly, or instead when it is too long to quote."""
    return json.dumps(value) if len(value) <= CORRECTION_CHARS else instead


class Diagnosis:
    """The diagnosis of one failed call, from its tool, its input and its error text."""

    def __init__(self, failed: Failed, ctx: Context, options: Mapping[str, Any]) -> None:
        self.failed, self.ctx, self.options = failed, ctx, options
        raw = failed.tool_input.get("file_path") or failed.tool_input.get("path")
        self.path = paths.normalise(raw, failed.cwd, ctx.platform) if isinstance(raw, str) and raw else None

    def result(self, code: Code, message: str, fix: Fix | None = None, **evidence) -> Result:
        return Result.of(code, message, self.failed.tool, self.ctx.platform.os, file=self.path, fix=fix,
                         evidence=evidence, severity=Severity.WARNING)

    def results(self) -> tuple[Result, ...]:
        error, tool = self.failed.error, self.failed.tool
        if MISSING.search(error):
            return self.missing()
        if tool == "Read" and TOO_LARGE.search(error):
            return self.too_large()
        if tool == "Grep" and PATTERN.search(error):
            return self.pattern()
        if tool in ("Grep", "Glob") and (timed := TIMED_OUT.search(error)):
            return self.too_broad(int(timed[1]))
        if tool != "Edit" and not (tool == "Write" and CHANGED in error):
            return ()
        if NOT_FOUND in error:
            return self.anchor_missing()
        if AMBIGUOUS.search(error):
            return self.anchor_ambiguous()
        if IDENTICAL in error or CHANGED in error:
            return self.stale(identical=IDENTICAL in error)
        return ()

    def file(self) -> tuple[str, bytes] | None:
        if self.path is None:
            return None
        try:
            data = self.ctx.fs.read_bytes(self.path)
        except OSError:
            return None
        return file_text(data), data

    def old_string(self) -> str:
        old = self.failed.tool_input.get("old_string")
        return file_text(old.encode("utf-8")) if isinstance(old, str) else ""

    def anchor_missing(self) -> tuple[Result, ...]:
        found, old = self.file(), self.old_string()
        if found is None or not old:
            return ()
        body, data = found
        name, eol = self.path.name, profile(data).eol.value
        endings = f"{name} uses {eol} line endings."
        candidates = anchors.closest(body, old)
        if not candidates:
            message = (f"old_string of the refused Edit is not in {name}, and no lines there come close. "
                       f"{endings}")
            return (self.result(Code.ANCHOR_NOT_FOUND, message),)
        best = candidates[0]
        lines = [best.match.first_line, best.match.last_line]
        if best.exact and len(candidates) == 1:
            view = text.snippet(body, best.match.first_line, best.match.last_line, 0)
            message = (f"old_string of the refused Edit matches {span(best.match)} of {name} once spaces and "
                       f"tabs are ignored. {endings} The file reads:\n{view}")
            fix = Fix("Edit", {**self.failed.tool_input, "old_string": best.text},
                      f"Call Edit again with old_string {quoted(best.text, 'copied from those lines')}.")
            return (self.result(Code.ANCHOR_NOT_FOUND, message, fix, lines=lines, exact=True),)
        if best.exact:
            return self.places(body, [candidate.match for candidate in candidates],
                               " once spaces and tabs are ignored")
        others = ", ".join(span(candidate.match) for candidate in candidates[1:])
        view = text.snippet(body, best.match.first_line, best.match.last_line, 1)
        message = (f"old_string of the refused Edit is not in {name}. The closest is {span(best.match)}, "
                   f"{best.score:.0%} alike" + (f", then {others}" if others else "") + f". {endings} "
                   f"{span(best.match).capitalize()} read:\n{view}")
        fix = Fix("Edit", {}, MARKED)
        return (self.result(Code.ANCHOR_NOT_FOUND, message, fix, lines=lines, exact=False),)

    def anchor_ambiguous(self) -> tuple[Result, ...]:
        found, old = self.file(), self.old_string()
        if found is None or not old:
            return ()
        return self.places(found[0], list(anchors.find(found[0], old)), "")

    def places(self, body: str, matches: list[anchors.Match], how: str) -> tuple[Result, ...]:
        """ANCHOR_AMBIGUOUS for old_string found in several places, with the first place's unique anchor."""
        if not matches:
            return ()
        views = "\n".join(f"{span(match)}:\n{text.snippet(body, match.first_line, match.last_line, 1)}"
                          for match in matches[:SHOWN])
        more = f", and {len(matches) - SHOWN} more" if len(matches) > SHOWN else ""
        message = (f"old_string of the refused Edit is in {self.path.name} {len(matches)} times{how}{more}:\n"
                   f"{views}")
        unique = anchors.unique_anchor(body, matches[0])
        said = quoted(unique, "longer, with the lines around it")
        fix = Fix("Edit", {**self.failed.tool_input, "old_string": unique},
                  f"For the first place, call Edit with old_string {said}. For another, lengthen old_string "
                  f"the same way, or set replace_all to true for all of them.")
        return (self.result(Code.ANCHOR_AMBIGUOUS, message, fix,
                            lines=[match.first_line for match in matches]),)

    def stale(self, identical: bool) -> tuple[Result, ...]:
        found, old = self.file(), self.old_string()
        if found is None:
            return ()
        body, name = found[0], self.path.name
        matches = anchors.find(body, old) if old else ()
        view = ""
        if len(matches) == 1:
            match = matches[0]
            lines = text.snippet(body, match.first_line, match.last_line)
            view = f" {span(match).capitalize()} read now:\n{lines}"
        if identical:
            message = (f"old_string and new_string of the refused Edit are the same, so {name} needs no "
                       f"change there.{view}")
        else:
            message = f"{name} changed after the last Read, so the {self.failed.tool} was refused.{view}"
        return (self.result(Code.STALE_VIEW, message),)

    def missing(self) -> tuple[Result, ...]:
        if self.path is None:
            return ()
        cwd, tool = self.failed.cwd, self.failed.tool
        where = shown(self.path, cwd)
        if tool in ("Grep", "Glob"):
            folder = self.existing(self.path)
            message = f"{where} does not exist. The nearest folder that does is {shown(folder, cwd)}."
            fix = Fix(tool, {}, f"Call {tool} again with a path under that folder.")
            return (self.result(Code.PATH_NOT_FOUND, message, fix, nearest=folder.as_posix()),)
        nearby = self.nearby()
        if nearby:
            listed = ", ".join(shown(path, cwd) for path in nearby[:SHOWN])
            message = f"{where} does not exist. Paths with the same name: {listed}."
            fix = Fix(tool, {}, f"Call {tool} again with one of those paths.")
        else:
            message = f"{where} does not exist, and no file named {self.path.name} is near it."
            fix = Fix("Glob", {"pattern": f"**/{self.path.name}"},
                      f"Glob for **/{self.path.name} to find where it is.")
        return (self.result(Code.PATH_NOT_FOUND, message, fix, nearby=[path.as_posix() for path in nearby]),)

    def nearby(self) -> tuple[Path, ...]:
        """Files with the missing path's name: the repository's, else those under the nearest folder that
        exists, the ones that share the most folders with the missing path first."""
        name = self.path.name.casefold()
        try:
            root = self.ctx.git.root(self.failed.cwd)
            known = self.ctx.git.ls_files(root) if root is not None else ()
        except GitError:
            known = ()
        found = [path for path in known if path.name.casefold() == name]
        if not found:
            folder = self.existing(self.path.parent)
            found = list(self.ctx.fs.find_named(folder, self.path.name, self.options["find_limit"]))
        wanted = self.path.parts
        return tuple(sorted(found, key=lambda path: -sum(1 for part in path.parts if part in wanted)))

    def existing(self, path: Path) -> Path:
        """path, or the nearest folder above it that exists."""
        while not self.ctx.fs.exists(path) and path != path.parent:
            path = path.parent
        return path

    def too_large(self) -> tuple[Result, ...]:
        found = self.file()
        if found is None:
            return ()
        data, name = found[1], self.path.name
        lines = data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
        per_part = max(50, min(2_000, self.options["part_bytes"] * max(lines, 1) // max(len(data), 1)))
        starts = ", ".join(f"{start:,}" for start in range(1, min(lines, per_part * 4) + 1, per_part))
        message = f"{name} holds {len(data):,} bytes in {lines:,} lines, more than one Read returns."
        fix = Fix("Read", {"file_path": str(self.path), "offset": 1, "limit": per_part},
                  f"Read it in parts of {per_part:,} lines, with limit {per_part:,} and offset {starts} and "
                  f"on.")
        return (self.result(Code.READ_TOO_LARGE, message, fix, lines=lines, bytes=len(data)),)

    def pattern(self) -> tuple[Result, ...]:
        given = self.failed.tool_input.get("pattern")
        if not isinstance(given, str):
            return ()
        reason = next((line.strip() for line in reversed(self.failed.error.splitlines())
                       if line.strip().startswith("error:")), "a regex parse error")
        if LOOK_AROUND.search(self.failed.error):
            fix = Fix("Grep", {}, "Rewrite the pattern without look-around or backreferences, which "
                                  "ripgrep's default engine lacks.")
        else:
            literal = RG_META.sub(r"\\\1", given)
            fix = Fix("Grep", {**self.failed.tool_input, "pattern": literal},
                      f"To search for the text as written, call Grep with the pattern {json.dumps(literal)}.")
        message = f"ripgrep rejected the pattern {json.dumps(given)}: {reason.removeprefix('error: ')}."
        return (self.result(Code.PATTERN_INVALID, message, fix),)

    def too_broad(self, seconds: int) -> tuple[Result, ...]:
        where = shown(self.path, self.failed.cwd) if self.path is not None else "the current folder"
        message = f"The {self.failed.tool} search in {where} ran out of time after {seconds} seconds."
        return (self.result(Code.SEARCH_TOO_BROAD, message),)


OPTIONS = {"find_limit": ConfigKey(int, FIND_LIMIT, "The most folder entries a search for a missing file's "
                                   "name walks."),
           "part_bytes": ConfigKey(int, PART_BYTES, "The bytes of one Read part io-guard suggests for a file "
                                   "too large to read whole.")}


def decided(check_id: str, found: tuple[Result, ...]) -> Decision:
    return Decision(check_id, Verdict.ALLOW, results=found) if found else Decision.observe(check_id)


class DiagnoseFailure(Check):
    meta = CheckMeta(
        id="diagnose.failure", layer=Layer.READ, events=frozenset({HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset({Tool.READ, Tool.GREP, Tool.GLOB, Tool.EDIT, Tool.WRITE}),
        platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING, cost=Cost.MEDIUM,
        reads=frozenset({"file_path", "path", "pattern", "old_string"}), writes=frozenset(),
        after=frozenset(), config=OPTIONS,
        codes=frozenset({Code.PATH_NOT_FOUND, Code.READ_TOO_LARGE, Code.PATTERN_INVALID,
                         Code.SEARCH_TOO_BROAD, Code.ANCHOR_NOT_FOUND, Code.ANCHOR_AMBIGUOUS,
                         Code.STALE_VIEW}),
        description="Answers a failed Read, Grep, Glob, Edit or Write with the path, the part or the pattern "
                    "that works.")

    def run(self, event: Event, ctx: Context) -> Decision:
        failed = Failed(event.tool_name, event.tool_input, event.error or "", event.cwd)
        return decided(self.meta.id, Diagnosis(failed, ctx, self.options).results())


class DiagnoseRefused(Check):
    meta = CheckMeta(
        id="diagnose.refused", layer=Layer.STALE,
        events=frozenset({HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset(), platforms=frozenset({"win32", "darwin"}), severity=Severity.WARNING,
        cost=Cost.MEDIUM, reads=frozenset(), writes=frozenset(), after=frozenset(),
        config={**OPTIONS,
                "tail_bytes": ConfigKey(int, TAIL_BYTES, "The bytes at the end of the transcript read for "
                                        "calls Claude Code refused before any hook ran.")},
        codes=frozenset({Code.PATH_NOT_FOUND, Code.ANCHOR_NOT_FOUND, Code.ANCHOR_AMBIGUOUS, Code.STALE_VIEW}),
        description="Answers an Edit or Write that Claude Code refused before any hook ran, at the next "
                    "hook.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.transcript is None:
            return Decision.observe(self.meta.id)
        try:
            tail = ctx.fs.read_tail(event.transcript, self.options["tail_bytes"])
        except OSError:
            return Decision.observe(self.meta.id)
        if b"<tool_use_error>" not in tail:
            return Decision.observe(self.meta.id)
        found: list[Result] = []
        for refusal in transcript.refusals(tail):
            if not ctx.session.first_time(f"refused:{refusal.tool_use_id}"):
                continue
            cwd = Path(refusal.cwd) if refusal.cwd else event.cwd
            failed = Failed(refusal.tool, refusal.tool_input, refusal.error, cwd)
            found.extend(Diagnosis(failed, ctx, self.options).results())
        return decided(self.meta.id, tuple(found))
