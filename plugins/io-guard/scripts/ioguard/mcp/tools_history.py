"""io.snapshot, io.restore and io.compare: the bytes of a batch of files kept before a task, put back file by
file, or compared with the files now.

Agents copied files into before-folders before a risky pass, 722 files in one session, undid a mistake with
git checkout, which threw away every other edit of the file (GIT-6), and built a checker per pass to show a
comment pass changed no code (VFY-6). io.snapshot keeps the files' bytes in io-guard's folder under a tag for
seven days. io.restore writes them back, only the files asked for and only those that changed. A restore
replaces edits made after the snapshot, so the PreToolUse hook on its call puts it to the user first
(checks.restore_ask), and io.restore writes nothing the hook did not ask about. io.compare reads each file's
code through lib.code_tokens and names the first place it differs.
"""
import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath

from ioguard.lib import code_tokens, paths, snapshots
from ioguard.lib.context import Context, read_or_none
from ioguard.lib.journal import text_of
from ioguard.lib.results import Code, Fix, callable_name
from ioguard.mcp.in_place import NOTE, held, refused
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolSpec, doc

GLOB = frozenset("*?[")


@dataclass(frozen=True)
class SnapshotInput:
    paths: list[str] = doc("Files, folders or globs such as src/**/*.cpp, absolute or from the project "
                           "folder. A folder takes every file under it, outside .git.")
    tag: str = doc("A name for the task the snapshot comes before, such as comment-pass. io.restore and "
                   "io.compare find the newest snapshot by it.")


@dataclass(frozen=True)
class SnapshotOutput:
    snapshot: str = doc("The snapshot's id, which io.restore and io.compare take as well as the tag.")
    tag: str = doc("The tag the snapshot is kept under.")
    files: int = doc("How many files the snapshot holds.")
    bytes: int = doc("How many bytes the snapshot holds.")
    expires: str = doc("When io-guard deletes the snapshot, seven days after it was taken.")

    def render(self) -> str:
        return (f"Kept {self.files:,} files, {self.bytes:,} bytes, as {self.tag}, snapshot {self.snapshot}. "
                f"io.restore and io.compare take the tag until {self.expires}.")


@dataclass(frozen=True)
class RestoreInput:
    tag: str = doc("The tag io.snapshot kept the files under, or the snapshot's id.")
    paths: list[str] = doc("Only these files, absolute or from the project folder. Left out, every file the "
                           "snapshot holds.", default_factory=list)


@dataclass(frozen=True)
class RestoreOutput:
    snapshot: str = doc("The snapshot's id.")
    restored: list[str] = doc("The files written back to their bytes in the snapshot.")
    unchanged: list[str] = doc("The files that already held those bytes, so nothing was written.")
    note: str = doc("What the built-in Edit tool needs before its next use of a restored file.")

    def render(self) -> str:
        head = (f"Restored {len(self.restored):,} files from snapshot {self.snapshot}"
                + (f", and {len(self.unchanged):,} already matched it." if self.unchanged else "."))
        return "\n".join([head, *self.restored, self.note])


@dataclass(frozen=True)
class CompareInput:
    tag: str = doc("The tag io.snapshot kept the files under, or the snapshot's id.")
    mode: str = doc("code ignores comments, docstrings and layout. includes ignores include and import lines "
                    "and their order. exact compares every line.", default="code")
    paths: list[str] = doc("Only these files, absolute or from the project folder. Left out, every file the "
                           "snapshot holds.", default_factory=list)


@dataclass(frozen=True)
class Difference:
    path: str = doc("The file.")
    how: str = doc("How it was compared: code, includes, or exact for a kind of file io-guard has no rules "
                   "for in this mode.")
    before_line: int = doc("The first line that differs in the snapshot's copy, from 1. 0 where that copy "
                           "has ended.")
    after_line: int = doc("The same place in the file now, from 1. 0 where the file has ended or is gone.")
    before: str = doc("The snapshot's line, cut at 200 characters.")
    after: str = doc("The line now, cut at 200 characters.")
    includes_added: list[str] = doc("Include lines the file gained, in includes mode.", default_factory=list)
    includes_removed: list[str] = doc("Include lines the file lost, in includes mode.", default_factory=list)


@dataclass(frozen=True)
class CompareOutput:
    snapshot: str = doc("The snapshot's id.")
    mode: str = doc("The mode the files were compared in.")
    same: list[str] = doc("The files that hold the same code as the snapshot, as the mode reads it.")
    differ: list[Difference] = doc("The files that do not, each with the first place they differ.")

    def render(self) -> str:
        total = len(self.same) + len(self.differ)
        head = f"{len(self.same):,} of {total:,} files hold the same code as snapshot {self.snapshot}, " \
               f"compared as {self.mode}."
        lines = [head]
        for each in self.differ:
            where = (f"line {each.after_line:,}, line {each.before_line:,} in the snapshot"
                     if each.after_line and each.before_line else "its end")
            lines.append(f"{each.path} differs at {where}, compared as {each.how}: "
                         f"{json.dumps(each.before)} became {json.dumps(each.after)}.")
            lines += [f"  gained {line}" for line in each.includes_added]
            lines += [f"  lost {line}" for line in each.includes_removed]
        return "\n".join(lines)


def gathered(raw: list[str], cwd: Path, ctx: Context, limit: int, tool: str) -> list[Path]:
    """Every file raw names, sorted, at most limit + 1 so a caller sees when there are more."""
    found: set[Path] = set()
    for each in raw:
        if GLOB & set(each):
            pattern, sensitive = each.replace("\\", "/"), not ctx.platform.case_insensitive
            matched = [path for path in ctx.fs.files_under(cwd, limit)
                       if PurePosixPath(path.relative_to(cwd).as_posix()).full_match(
                           pattern, case_sensitive=sensitive)]
        else:
            path = paths.normalise(each, cwd, ctx.platform)
            matched = list(ctx.fs.files_under(path, limit)) or ([path] if ctx.fs.stat(path) else [])
        if not matched:
            first = Fix("Glob", {"pattern": each}, "Glob for the files to keep first.")
            raise refused(Code.PATH_NOT_FOUND, f"{each} names no file, so {tool} kept nothing.", tool,
                          Path(each), ctx, first)
        found.update(matched)
        if len(found) > limit:
            break
    return sorted(found)[:limit + 1]


def home_of(ctx: Context) -> Path:
    if ctx.data_dir is None:
        raise RuntimeError("io.snapshot and io.restore need io-guard's folder, which this context lacks.")
    return ctx.data_dir


def snapshot(given: SnapshotInput, call: ToolCall) -> SnapshotOutput:
    ctx, tool = call.context, "io.snapshot"
    if not given.tag.strip() or not given.paths:
        raise InvalidArguments("io.snapshot takes at least one path and a tag that is not empty.")
    most_files, most_bytes = ctx.config.get("io.snapshot.max_files"), ctx.config.get("io.snapshot.max_bytes")
    found = gathered(given.paths, call.cwd, ctx, most_files, tool)
    fewer = Fix(callable_name(tool), {"tag": given.tag},
                "Call it on fewer paths, such as only the folders the task changes.")
    if len(found) > most_files:
        raise refused(Code.SNAPSHOT_TOO_LARGE, f"The paths hold more than {most_files:,} files, so {tool} "
                      f"kept nothing.", tool, call.cwd, ctx, fewer)
    files, total = [], 0
    for path in found:
        data = ctx.fs.read_bytes(path)
        total += len(data)
        if total > most_bytes:
            raise refused(Code.SNAPSHOT_TOO_LARGE, f"The paths hold more than {most_bytes:,} bytes, so "
                          f"{tool} kept nothing.", tool, call.cwd, ctx, fewer)
        files.append((path, data))
    now = ctx.clock.now()
    home = home_of(ctx)
    snapshots.sweep(home, now)
    kept = snapshots.take(home, given.tag, call.cwd, files, now)
    with ctx.session.lock:
        ctx.session.tag = given.tag
    return SnapshotOutput(kept.id, kept.tag, len(files), total, kept.expires.isoformat(timespec="seconds"))


def planned(tag: str, raw: list[str], call: ToolCall, tool: str) -> snapshots.Pending:
    """The snapshot tag names in this project, against the files raw names, or every file it holds. A tag
    no snapshot holds, or a path the snapshot never kept, refuses the call."""
    ctx = call.context
    found = snapshots.find(home_of(ctx), tag, call.cwd, ctx.clock.now())
    if found is None:
        again = Fix(callable_name("io.snapshot"), {"tag": tag},
                    f"Call io.snapshot before the next task, then {tool} with its tag.")
        raise refused(Code.HANDLE_EXPIRED, f"No snapshot in this project is tagged or named {tag}, so {tool} "
                      f"did nothing. A snapshot lasts seven days.", tool, call.cwd, ctx, again)
    wanted = [paths.normalise(each, call.cwd, ctx.platform) for each in raw] or None
    plan = snapshots.pending(found, wanted, partial(read_or_none, ctx.fs), ctx.platform.case_insensitive)
    if plan.unknown:
        names = ", ".join(kept.path.name for kept in found.files[:5])
        more = " and more" if len(found.files) > 5 else ""
        raise refused(Code.PATH_NOT_FOUND, f"Snapshot {found.id} holds no {plan.unknown[0].as_posix()}, so "
                      f"{tool} did nothing. It holds {names}{more}.", tool, plan.unknown[0], ctx)
    return plan


def restore(given: RestoreInput, call: ToolCall) -> RestoreOutput:
    ctx, tool = call.context, "io.restore"
    plan = planned(given.tag, given.paths, call, tool)
    found = plan.snapshot
    if plan.changed:
        with ctx.session.lock:
            asked = plan.key() in ctx.session.asked_restores
            ctx.session.asked_restores.discard(plan.key())
        if not asked:
            raise refused(Code.RESTORE_ASKED, f"{tool} wrote nothing, because no permission prompt put the "
                          f"restore of {len(plan.changed):,} changed files to the user.", tool, call.cwd, ctx)
    restored = []
    for kept in plan.changed:
        with held(kept.path, ctx, tool):
            try:
                ctx.fs.write_atomic(kept.path, found.blob(kept))
            except PermissionError:
                done = f" It had restored {', '.join(restored)}." if restored else ""
                raise refused(Code.FILE_LOCKED, f"Another program holds {kept.path.name} open, so {tool} "
                              f"could not replace it.{done}", tool, kept.path, ctx) from None
        restored.append(kept.path.as_posix())
    return RestoreOutput(found.id, restored, [kept.path.as_posix() for kept in plan.same], NOTE)


def line_of(text: str, number: int) -> str:
    """Line number of text, from 1, cut at 200 characters, or empty where the text has none."""
    lines = text.splitlines()
    return lines[number - 1][:200] if 0 < number <= len(lines) else ""


def compare(given: CompareInput, call: ToolCall) -> CompareOutput:
    ctx, tool = call.context, "io.compare"
    if given.mode not in code_tokens.MODES:
        raise InvalidArguments(f"mode must be one of {', '.join(code_tokens.MODES)}.")
    plan = planned(given.tag, given.paths, call, tool)
    same, differ = [kept.path.as_posix() for kept in plan.same], []
    for kept in plan.changed:
        before = text_of(plan.snapshot.blob(kept))
        now = read_or_none(ctx.fs, kept.path)
        if now is None:
            differ.append(Difference(kept.path.as_posix(), given.mode, 1 if before else 0, 0,
                                     line_of(before, 1), ""))
            continue
        after = text_of(now)
        found = code_tokens.compare(before, after, kept.path.suffix, given.mode)
        if found.same:
            same.append(kept.path.as_posix())
            continue
        differ.append(Difference(kept.path.as_posix(), found.how, found.before_line, found.after_line,
                                 line_of(before, found.before_line), line_of(after, found.after_line),
                                 list(found.added), list(found.removed)))
    return CompareOutput(plan.snapshot.id, given.mode, sorted(same), differ)


SPECS = (
    ToolSpec("io.snapshot", "Keep files before a task",
             "Keeps the bytes of files, folders or globs in io-guard's folder under a tag, for seven days. "
             "Use it before a pass over many files, so io.restore can undo it file by file and io.compare "
             "can show what changed.",
             SnapshotInput, SnapshotOutput, read_only=False, destructive=False, idempotent=False,
             handler=snapshot),
    ToolSpec("io.restore", "Put files back as a snapshot kept them",
             "Writes files back to the bytes io.snapshot kept, only the ones asked for and only those that "
             "changed, and asks the user first. Use it to undo a task without git checkout, which loses "
             "every other edit of the file.",
             RestoreInput, RestoreOutput, read_only=False, destructive=True, idempotent=True,
             handler=restore),
    ToolSpec("io.compare", "Show whether a pass changed code",
             "Compares files with the snapshot io.snapshot kept, ignoring comments, docstrings and layout, "
             "or include lines and their order, and names the first place each file's code differs. Use it "
             "to prove a comment or include pass changed no code.",
             CompareInput, CompareOutput, read_only=True, destructive=False, idempotent=True,
             handler=compare),
)
