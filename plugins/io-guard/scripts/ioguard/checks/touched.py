"""Tell the agent which files a shell command changed, and what it did to the bytes of the ones it had read.

A formatter, a script or git can change a file behind the agent's back (STL-1, BYT-2), and an Edit after
that still applies (context.md, "Hooks and MCP", row 5), so this is the one warning the agent gets. Before a
Bash or PowerShell command the check keeps git status for the session's repository, and the size and time of
each file the agent has read or written. After it, a read file whose size or time moved is named with the step
to read it again, and verify.write's comparison with its last profile names what the command did to its
endings, BOM, encoding or indent. New untracked files are named (GIT-2), and so are tracked files the command
changed or deleted. A bashEditDiff in the tool's response, which Claude Code sends only with
bashEditDiffEnabled, adds its files. Changes under the skip_trees globs are left out. So is a change to git's
index alone: a listed file whose status moved while its size and time did not, as git add, git commit and git
reset leave one, and a file git removed from the index that is still on disk. A file that moved, by git
status's rename or by a path gone and a new one with the same name and size, is named as moved, and not at all
when the command itself names a move, such as git mv, mv or Move-Item, even when a commit in it hides where
the file went. A file the session's own Edit, Write or io tool wrote while the command ran is not the
command's, and when another shell command started while it ran, the message says either one may have made
the change. The advice holds one step for each kind of change that needs one: read a read file again, before
the next Edit, or to see it when it is an image or other binary file, delete a new file the task does not
need, and use a moved file's new path. A path in the session's scratchpad is shown from it. A tracked file
that changed while an interpreter ran a script file also gets SHELL_WRITE, because that write skipped the
checks an Edit gets, unless a git command in the same command could have changed it.
"""
import fnmatch
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.checks.shell_writes import located, resolve, tracked
from ioguard.checks.verify_write import Written, compare
from ioguard.lib import commit_message, paths, pwsh, shell
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context, ShellSnapshot, repository_root
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.git import GitError, StatusEntry
from ioguard.lib.profile import profile
from ioguard.lib.results import Code, Fix, Layer, Result, Severity, callable_name

LISTED = 8                   # paths each part of the report names before it gives the rest as a count
TREE_WRITERS = frozenset({"am", "apply", "cherry-pick", "merge", "pull", "rebase", "revert", "switch"})
RESET_TREE = frozenset({"--hard", "--merge", "--keep"})
STASH_READS = frozenset({"list", "show"})
MOVERS = frozenset({"mv", "move", "move-item", "mi", "ren", "rename", "rename-item", "rni"})


def git_changes(simple: shell.SimpleCommand, cwd: Path | None, ctx: Context) -> frozenset[Path] | None:
    """The files a git command can change in the working tree: the paths it names, none, or None when it can
    change any file. git rm is left out, since it only deletes."""
    at = commit_message.subcommand(simple.words)
    if at is None:
        return frozenset()
    name, rest = simple.words[at], simple.words[at + 1:]
    match name:
        case "mv" | "restore":
            given = [word for word in rest if not word.startswith("-")]
        case "checkout" if "--" in rest:
            given = list(rest[rest.index("--") + 1:])
        case "checkout":
            return None                               # a branch or a path, and a branch changes any file
        case "reset":
            return None if RESET_TREE & set(rest) else frozenset()
        case "stash":
            return frozenset() if rest[:1] and rest[0] in STASH_READS else None
        case _:
            return None if name in TREE_WRITERS else frozenset()
    found = [resolve(word, cwd, ctx) for word in given]
    return None if None in found else frozenset(found)


def names_a_move(event: Event) -> bool:
    """Whether the command runs mv, git mv, Move-Item or another command whose job is to move a file."""
    command = event.command or ""
    simples = pwsh.commands(command) if event.tool is Tool.POWERSHELL else shell.commands(command)
    for simple in simples:
        at = commit_message.subcommand(simple.words)
        if simple.name.lower() in MOVERS or (at is not None and simple.words[at] == "mv"):
            return True
    return False


def moves(gone: list[Path], arrived: list[Path], renamed: dict[Path, Path], sizes: dict[Path, int | None],
          named_move: bool, ctx: Context) -> list[tuple[Path, Path]]:
    """Each file that left one path and arrived at another: a rename git status names, or a path gone and a
    path new with the same file name, and the same size where the size before is known, or a command that
    names a move where it is not."""
    def same_file(old: Path, new: Path) -> bool:
        before, now = sizes.get(old), ctx.fs.stat(new)
        if old.name != new.name:
            return False
        return before == now.size if before is not None and now is not None else named_move

    pairs = [(renamed[path], path) for path in arrived if path in renamed]
    left = [path for path in gone if path not in {old for old, _ in pairs}]
    for path in (path for path in arrived if path not in renamed):
        match = next((old for old in left if same_file(old, path)), None)
        if match is not None:
            pairs.append((match, path))
            left.remove(match)
    return pairs


def vanished(before: ShellSnapshot, after: frozenset[tuple[str, str]] | None, ctx: Context) -> list[Path]:
    """The paths git status listed before the command, such as an untracked or a newly added file, that it
    lists no more and that are gone from disk. git leaves no D entry for a file it never committed, so a
    move of one shows only here."""
    if before.root is None or before.status is None or after is None:
        return []
    now = {name for name, _ in after}
    return [before.root / name for name, _ in sorted(before.status)
            if name not in now and not ctx.fs.exists(before.root / name)]


def under(path: Path, folders: frozenset[Path]) -> bool:
    return any(path == folder or path.is_relative_to(folder) for folder in folders)


def status(ctx: Context, root: Path | None) -> tuple[StatusEntry, ...] | None:
    """git status from root, or None when git cannot say."""
    if root is None:
        return None
    try:
        return ctx.git.status(root).entries
    except GitError:
        return None


def codes(entries: tuple[StatusEntry, ...] | None) -> frozenset[tuple[str, str]] | None:
    """Each changed or untracked path with its XY code."""
    if entries is None:
        return None
    return frozenset((entry.path, entry.index + entry.worktree) for entry in entries)


def listed_paths(entries: tuple[StatusEntry, ...] | None) -> set[str]:
    """Every path git status names, a rename's old path too."""
    return {name for entry in entries or () for name in (entry.path, entry.original) if name}


def in_words(items: list[str]) -> str:
    """"a", "a and b", "a, b and c"."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def named(found: list[Path], cwd: Path, limit: int, scratchpad: Path | None = None) -> str:
    """Paths for a message: "a.cpp", "a.cpp and b.h", "a, b, c and 4 more"."""
    shown = [paths.shown(path, cwd, scratchpad) for path in found[:limit]]
    rest = len(found) - len(shown)
    return in_words(shown + [f"{rest} more"] if rest else shown)


class Touched(Check):
    meta = CheckMeta(
        id="shell.touched", layer=Layer.STALE,
        events=frozenset({HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL, Tool.EDIT, Tool.WRITE}),
        platforms=frozenset({"win32", "darwin"}),
        severity=Severity.WARNING, cost=Cost.EXPENSIVE, reads=frozenset({"command"}), writes=frozenset(),
        after=frozenset(), config={"listed": ConfigKey(int, LISTED, "The paths each part of the report names "
                                                       "before it gives the rest as a count.")},
        codes=frozenset({Code.TOUCHED_BY_SHELL, Code.EOL_MISMATCH, Code.BOM_CHANGED, Code.ENCODING_INVALID,
                         Code.CONTROL_BYTES_ADDED, Code.INDENT_MISMATCH, Code.SHELL_WRITE}),
        description="Tells the agent which files a shell command changed, and what it did to their bytes.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.tool in (Tool.EDIT, Tool.WRITE):
            if event.kind is HookEvent.POST_TOOL_USE and event.file_path is not None:
                ctx.session.wrote(event.file_path)
            return Decision.observe(self.meta.id)
        if event.tool_use_id is None:
            return Decision.observe(self.meta.id)
        if event.kind is HookEvent.PRE_TOOL_USE:
            root = repository_root(ctx.git, event.cwd)
            with ctx.session.lock:
                read = list(ctx.session.read_profiles)
                step = ctx.session.shell_started = ctx.session.next_step()
            found = status(ctx, root)
            listed = {root / name: ctx.fs.stat(root / name) for name in listed_paths(found)}
            snapshot = ShellSnapshot(root, codes(found), {path: ctx.fs.stat(path) for path in read}, listed,
                                     step)
            ctx.session.keep_snapshot(event.tool_use_id, snapshot)
            return Decision.observe(self.meta.id)
        before = ctx.session.take_snapshot(event.tool_use_id)
        if not isinstance(before, ShellSnapshot):
            return Decision.observe(self.meta.id)
        found = self.report(before, event, ctx)
        if not found:
            return Decision.observe(self.meta.id)
        return Decision(self.meta.id, Verdict.ALLOW, results=found)

    def report(self, before: ShellSnapshot, event: Event, ctx: Context) -> tuple[Result, ...]:
        skipped = ctx.config.get("skip_trees")
        own = ctx.session.written_since(before.step)
        with ctx.session.lock:
            beside = ctx.session.shell_started > before.step

        def kept(path: Path) -> bool:
            relative = paths.shown(path, before.root) if before.root is not None else path.as_posix()
            return path not in own and not any(fnmatch.fnmatch(relative, glob) for glob in skipped)

        moved = {path: ctx.fs.stat(path) for path, stat in before.stats.items() if kept(path)}
        read = sorted(path for path, stat in moved.items() if stat is not None and stat != before.stats[path])
        read += sorted(path for path in self.diffed(event)
                       if path in before.stats and path not in read and kept(path))
        deleted = sorted(path for path, stat in moved.items()
                         if stat is None and before.stats[path] is not None)
        by_status = set()
        created, changed, added = [], [], []
        entries = status(ctx, before.root)
        after = codes(entries)
        renamed = {before.root / entry.path: before.root / entry.original for entry in entries or ()
                   if entry.original and before.root is not None}
        if before.status is not None and after is not None:
            unindexed = {name for name, code in after if code[0] == "D" and ctx.fs.exists(before.root / name)}
            for name, code in sorted(after - before.status):
                path = before.root / name
                if not kept(path) or path in read or path in deleted or name in unindexed:
                    continue
                if path in before.listed and ctx.fs.stat(path) == before.listed[path]:
                    continue
                (created if code == "??" else deleted if "D" in code else
                 added if code[0] in "AR" else changed).append(path)
                if "D" in code:
                    by_status.add(path)
        sizes = {path: stat.size for path, stat in (*before.stats.items(), *before.listed.items()) if stat}
        named_move = names_a_move(event)
        gone = deleted + vanished(before, after, ctx)
        moved = moves(gone, created + added, renamed, sizes, named_move, ctx)
        deleted = [path for path in deleted if path not in {old for old, _ in moved}]
        if named_move:
            deleted = [path for path in deleted if path in by_status]
        created = [path for path in created if path not in {new for _, new in moved}]
        changed += [path for path in added if path not in {new for _, new in moved}]
        limit, cwd, scratch = self.options["listed"], event.cwd, event.scratchpad

        def listed(found: list[Path]) -> str:
            return named(found, cwd, limit, scratch)

        shown_moves = [] if named_move else [f"{paths.shown(old, cwd, scratch)} to "
                                             f"{paths.shown(new, cwd, scratch)}" for old, new in moved]
        parts = ([f"changed {listed(read)}, read before it"] if read else []) + \
                ([f"changed {listed(changed)}"] if changed else []) + \
                ([f"created {listed(created)}"] if created else []) + \
                ([f"deleted {listed(deleted)}"] if deleted else []) + \
                ([f"moved {in_words(shown_moves[:limit])}"] if shown_moves else [])
        if not parts:
            return ()
        with ctx.session.lock:
            binary = [path for path in read if (seen := ctx.session.read_profiles.get(path)) and seen.binary]
        text = [path for path in read if path not in binary]
        steps = ([f"Read {listed(text)} again before the next Edit."] if text else []) + \
                ([f"Read {listed(binary)} again to see what the command made of it."] if binary else []) + \
                (["Delete any new file the task does not need, and keep the rest on purpose."]
                 if created else []) + \
                (["Use the files' new paths from now on."] if shown_moves else [])
        actor = "This command, or another command that ran at the same time," if beside else "This command"
        found = [Result.of(Code.TOUCHED_BY_SHELL, f"{actor} {in_words(parts)}.", event.tool_name,
                           ctx.platform.os,
                           fix=Fix("Read", {}, " ".join(steps)) if steps else None,
                           evidence={"read": [path.as_posix() for path in read],
                                     "changed": [path.as_posix() for path in changed],
                                     "created": [path.as_posix() for path in created],
                                     "deleted": [path.as_posix() for path in deleted],
                                     "moved": [[old.as_posix(), new.as_posix()] for old, new in moved]})]
        for path in read:
            found.extend(self.drift(path, event, ctx))
        return tuple(found) + self.scripted([*read, *changed], event, ctx)

    @staticmethod
    def scripted(touched: list[Path], event: Event, ctx: Context) -> tuple[Result, ...]:
        """SHELL_WRITE for the tracked files a command changed while an interpreter ran a script file in it,
        since those writes skipped the checks an Edit gets. A file a git command in it names, as git mv
        does, is git's. A git command that can change any file, such as a branch checkout, leaves no script
        named. A redirect, sed -i, tee, cp or mv onto a tracked file never gets here, since shell.writes
        refuses it before it runs."""
        simples = shell.commands(event.command or "") if event.tool is Tool.BASH else ()
        runs = [run for simple in simples if (run := shell.script_run(simple))]
        if not runs:
            return ()
        command = event.command or ""
        by_git = [git_changes(simple, cwd, ctx)
                  for simple, cwd in located(command, shell.scan(command), event.cwd, ctx)]
        if None in by_git:
            return ()
        named_by_git = frozenset().union(*by_git)
        written = [path for path in touched if tracked(path, ctx) and not under(path, named_by_git)]
        if not written:
            return ()
        batch, script = callable_name("io.edit"), runs[0].script
        files = named(written, event.cwd, LISTED)
        message = (f"{script} changed {files}, which git tracks, so those writes skipped io-guard's byte "
                   f"checks and Claude Code's checkpoints.")
        given = {resolve(word, event.cwd, ctx) for run in runs for word in run.arguments}
        if given.isdisjoint(written):
            fix = Fix(script, {}, f"Change {files} by changing {script} or what it reads, then run it again.")
        else:
            fix = Fix(batch, {}, f"Make the next change to them with {batch} or the Edit tool.")
        return (Result.of(Code.SHELL_WRITE, message, event.tool_name, ctx.platform.os,
                          severity=Severity.WARNING, fix=fix,
                          evidence={"script": script, "files": [path.as_posix() for path in written]}),)

    @staticmethod
    def diffed(event: Event) -> list[Path]:
        """The files a bashEditDiff in the tool's response names, when Claude Code sent one."""
        listed = (event.tool_response or {}).get("files")
        if not isinstance(listed, list):
            return []
        return [paths.normalise(entry["filePath"], event.cwd, event.platform) for entry in listed
                if isinstance(entry, dict) and isinstance(entry.get("filePath"), str)]

    @staticmethod
    def drift(path: Path, event: Event, ctx: Context) -> tuple[Result, ...]:
        """What the command did to a read file's bytes, against the profile the agent last had of it."""
        with ctx.session.lock:
            last = ctx.session.read_profiles.get(path)
        try:
            data = ctx.fs.read_bytes(path)
        except OSError:
            return ()
        with ctx.session.lock:
            ctx.session.read_profiles[path] = profile(data)
        if last is None or last.binary:
            return ()
        return compare(Written(path, "This command", last, None, data, None, False), event.tool_name,
                       ctx.platform.os, 0)
