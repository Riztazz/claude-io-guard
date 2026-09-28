"""io.snapshot and io.restore: the bytes of a batch of files kept before a task, and put back file by file.

Agents copied files into before-folders before a risky pass, 722 files in one session, and undid a mistake
with git checkout, which threw away every other edit of the file (GIT-6). io.snapshot keeps the files' bytes
in io-guard's folder under a tag for seven days, and io.restore writes them back, only the files asked for
and only those that changed. A restore replaces edits made after the snapshot, so the PreToolUse hook on its
call puts it to the user first (checks.restore_ask), and io.restore writes nothing the hook did not ask about.
"""
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath

from ioguard.lib import paths, snapshots
from ioguard.lib.context import Context, read_or_none
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


def restore(given: RestoreInput, call: ToolCall) -> RestoreOutput:
    ctx, tool = call.context, "io.restore"
    found = snapshots.find(home_of(ctx), given.tag, call.cwd, ctx.clock.now())
    if found is None:
        again = Fix(callable_name("io.snapshot"), {"tag": given.tag},
                    "Call io.snapshot before the next task, then io.restore with its tag.")
        raise refused(Code.HANDLE_EXPIRED, f"No snapshot in this project is tagged or named {given.tag}, so "
                      f"{tool} wrote nothing. A snapshot lasts seven days.", tool, call.cwd, ctx, again)
    wanted = [paths.normalise(each, call.cwd, ctx.platform) for each in given.paths] or None
    plan = snapshots.pending(found, wanted, partial(read_or_none, ctx.fs), ctx.platform.case_insensitive)
    if plan.unknown:
        names = ", ".join(kept.path.name for kept in found.files[:5])
        more = " and more" if len(found.files) > 5 else ""
        raise refused(Code.PATH_NOT_FOUND, f"Snapshot {found.id} holds no {plan.unknown[0].as_posix()}, so "
                      f"{tool} wrote nothing. It holds {names}{more}.", tool, plan.unknown[0], ctx)
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
)
