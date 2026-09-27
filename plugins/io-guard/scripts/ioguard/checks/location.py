"""Where an Edit or Write lands: device names, read-only files, links into other repositories, files dirty at
session start, and the process that holds a file a write could not replace.

write.location runs before the tool. A file named for a Windows device, such as nul.txt, cannot be opened or
deleted by Windows tools (PTH-5), so it is refused on Windows. A read-only file is refused before the tool
fails on it or an editor stops the session at a prompt (LCK-4), with git lfs lock as the step when git
marks the file lockable. A path that runs through a junction or symbolic link into another repository goes
ahead with a note naming that repository, and when the session's own repository tracks the path, a discard,
stash or branch switch there writes through the link (context.md, "Git through a junction"), so that gets a
warning once per session. The first write to a file that already had changes when the session started gets
a line saying so, because those changes are not the agent's (STL-3). A write outside the project goes ahead
with nothing said (D27).

write.locks runs after an Edit or Write fails with EPERM, EBUSY or EACCES, which on Windows is a rename over
a file another process holds (LCK-1). It names that process through lib.locks, and the fix never points at a
shell write.
"""
import re
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import paths
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.git import GitError
from ioguard.lib.results import Code, Fix, Layer, Result, Severity

LOCK_ERROR = re.compile(r"\b(EPERM|EBUSY|EACCES)\b")


def root_of(ctx: Context, path: Path) -> Path | None:
    """The repository holding path, or None outside one or when git cannot say."""
    try:
        return ctx.git.root(path)
    except GitError:
        return None


def relative(path: Path, root: Path | None) -> str:
    try:
        return path.relative_to(root).as_posix() if root is not None else path.as_posix()
    except ValueError:
        return path.as_posix()


class Location(Check):
    meta = CheckMeta(
        id="write.location", layer=Layer.LOCATION, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.REFUSED, cost=Cost.MEDIUM, reads=frozenset({"file_path"}), writes=frozenset(),
        after=frozenset(), config={},
        codes=frozenset({Code.RESERVED_NAME, Code.READ_ONLY, Code.LINKED_PATH}),
        description="Refuses a write to a Windows device name or a read-only file, and names the repository "
                    "a linked path writes into.")

    def run(self, event: Event, ctx: Context) -> Decision:
        path = event.file_path
        if path is None:
            return Decision.observe(self.meta.id)
        device = paths.reserved(path) if ctx.platform.windows else None
        if device is not None:
            message = (f"{path.name} names the Windows device {device.upper()}, which Windows tools cannot "
                       f"open or delete as a file.")
            result = self.result(Code.RESERVED_NAME, message, event, ctx,
                                 fix=Fix(event.tool_name, {}, "Give the file another name."))
            return Decision(self.meta.id, Verdict.DENY, results=(result,))
        found = ctx.fs.stat(path)
        if found is not None and found.readonly:
            return Decision(self.meta.id, Verdict.DENY, results=(self.read_only(path, event, ctx),))
        results = self.linked(path, event, ctx)
        context = self.dirty(path, ctx)
        if not results and not context:
            return Decision.observe(self.meta.id)
        return Decision(self.meta.id, Verdict.ALLOW, results=results, context=context)

    @staticmethod
    def result(code: Code, message: str, event: Event, ctx: Context, **fields) -> Result:
        return Result.of(code, message, event.tool_name, ctx.platform.os, file=event.file_path, **fields)

    def read_only(self, path: Path, event: Event, ctx: Context) -> Result:
        """The refusal, with git lfs lock as the step when git marks the file lockable."""
        try:
            lockable = ctx.git.attributes(path).get("lockable") == "set"
        except GitError:
            lockable = False
        fix = None
        if lockable:
            name = relative(path, root_of(ctx, path))
            fix = Fix("Bash", {"command": f"git lfs lock {name}"},
                      f"Lock it with git lfs lock {name} from the repository root, then call "
                      f"{event.tool_name} again.")
        return self.result(Code.READ_ONLY, f"{path.name} is read-only.", event, ctx, fix=fix)

    def linked(self, path: Path, event: Event, ctx: Context) -> tuple[Result, ...]:
        """A note when path runs through a link into another repository, and a warning once per session when
        the session's own repository tracks it."""
        target = ctx.fs.link_target(path)
        owner = None if target is None else root_of(ctx, target)
        if owner is None:
            return ()
        project = root_of(ctx, event.cwd)
        if project is not None and owner == project:
            return ()
        found = [self.result(Code.LINKED_PATH, f"{path.name} is {target.as_posix()} through a link, in the "
                             f"repository at {owner.as_posix()}.", event, ctx,
                             evidence={"target": target.as_posix(), "owner": owner.as_posix()})]
        try:
            tracked = project is not None and ctx.git.is_tracked(path)
        except GitError:
            tracked = False
        if tracked and ctx.session.first_time(f"linked-tracked:{project}:{owner}"):
            message = (f"Git in {project.as_posix()} tracks {relative(path, project)} through the link, so a "
                       f"discard, stash or branch switch there writes into {owner.as_posix()}.")
            found.append(self.result(Code.LINKED_PATH, message, event, ctx,
                                     fix=Fix("Bash", {}, "Leave that path out of every discard, stash and "
                                                         "branch switch in this repository.")))
        return tuple(found)

    @staticmethod
    def dirty(path: Path, ctx: Context) -> tuple[str, ...]:
        """One line before the first write to a file that had changes when the session started."""
        dirty = ctx.probe.dirty_at_start or ()
        if path not in dirty or not ctx.session.first_time(f"dirty:{path}"):
            return ()
        return (f"io-guard: {path.name} already had uncommitted changes when this session started. Keep "
                f"those changes, and change only what this task needs.",)


class LockHolders(Check):
    meta = CheckMeta(
        id="write.locks", layer=Layer.LOCATION, events=frozenset({HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset({Tool.EDIT, Tool.WRITE}), platforms=frozenset({"win32", "darwin"}),
        severity=Severity.WARNING, cost=Cost.EXPENSIVE, reads=frozenset({"file_path"}), writes=frozenset(),
        after=frozenset(), config={}, codes=frozenset({Code.FILE_LOCKED}),
        description="Names the process that holds a file an Edit or Write could not replace.")

    def run(self, event: Event, ctx: Context) -> Decision:
        path, error = event.file_path, event.error or ""
        failure = LOCK_ERROR.search(error)
        if path is None or failure is None:
            return Decision.observe(self.meta.id)
        try:
            held = ctx.fs.holders(path)
        except OSError:
            held = None
        tool, name = event.tool_name, path.name
        if held:
            names = " and ".join(f"{process.name} (process {process.pid})" for process in held)
            verb = "holds" if len(held) == 1 else "hold"
            message = f"{names} {verb} {name} open, so the {tool} tool could not replace it."
        elif held is None:
            message = f"Another process holds {name} open, so the {tool} tool could not replace it."
        else:
            message = (f"Another process held {name} open, so the {tool} tool could not replace it. It had "
                       f"let go by the time io-guard looked.")
        holders = [{"pid": process.pid, "name": process.name} for process in held or ()]
        result = Result.of(Code.FILE_LOCKED, message, tool, ctx.platform.os, file=path,
                           evidence={"error": failure[1], "holders": holders})
        return Decision(self.meta.id, Verdict.ALLOW, results=(result,))
