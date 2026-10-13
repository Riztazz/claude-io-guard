"""Refuse a shell command that deletes outside the folders a session works in, or deletes one of them whole.

A shell delete skips Claude Code's checkpoints, and a wildcard can name more than the agent meant: on
Windows, Git Bash shows a folder named C + U+F03A as C:, so rm -rf C?/ deletes the drive. lib.deletes finds
each delete and resolves its targets the way the shell will, wildcards and links included. The allowed roots
are the git repository holding the working folder, or that folder outside git, the session scratchpad, the
temp folders, and the folders in checks.shell.deletes.roots. A delete is refused when a target, or the real
path a link leads to, is outside them; when a recursive delete names a root itself, a folder holding one, or
the repository's .git or a folder inside it; when a wildcard picks a path inside .git; when a target has no
path before the command runs, such as one built from a variable; and when the command also makes a link,
which can lead a path elsewhere by the time the delete runs. The refusal names each resolved path. A path
the system cannot resolve is refused too, and an error inside the check refuses a command that names a
delete, so no such input makes this check fail open.
"""
import re
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import paths
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.deletes import DELETE_WORDS, Delete, bash_deletes, makes_link, powershell_deletes, resolve
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.git import GitError
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.results import Code, Fix, Layer, Result, Severity
from ioguard.lib.writes import Host


class ShellDeletes(Check):
    meta = CheckMeta(
        id="shell.deletes", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH, Tool.POWERSHELL}), platforms=EVERY_PLATFORM,
        severity=Severity.REFUSED, cost=Cost.MEDIUM, reads=frozenset({"command"}), writes=frozenset(),
        after=frozenset(),
        config={"roots": ConfigKey(list, [], "More folders inside which a shell command may delete, besides "
                                             "the repository, the session scratchpad and the temp folders. "
                                             "A leading ~ is the home folder.",
                                   project_may_set=False),
                "shown": ConfigKey(int, 5, "The refused targets a message names before it counts the rest.")},
        codes=frozenset({Code.SHELL_DELETE}),
        description="Refuses a shell delete outside the repository, the scratchpad and the temp folder, of "
                    "one of them or .git whole, or of a path it cannot resolve before the command runs.")

    def run(self, event: Event, ctx: Context) -> Decision:
        command, roots = event.command or "", []
        try:
            refused, roots = self.refused(command, event, ctx)
        except Exception as error:          # this check fails closed on a command that names a delete
            if not DELETE_WORDS.search(command):
                raise
            refused = [f"io-guard could not read this command, which names a delete: "
                       f"{type(error).__name__}: {error}"]
        if not refused:
            return Decision.observe(self.meta.id)
        return Decision(self.meta.id, Verdict.DENY, results=(self.result(refused, roots, event, ctx),))

    def refused(self, command: str, event: Event, ctx: Context) -> tuple[list[str], list[Path]]:
        """Why each delete in the command is refused, and the allowed roots."""
        host, powershell = Host.of(ctx), event.tool is Tool.POWERSHELL
        found = (powershell_deletes(command, event.cwd, host) if powershell
                 else bash_deletes(command, event.cwd, host))
        if not found:
            return [], []
        repository = self.repository(event, ctx)
        roots = self.roots(repository, event, ctx)
        if makes_link(command, powershell):
            return ["the command makes a link or a junction, which can lead a path it deletes elsewhere by "
                    "the time the delete runs"], roots
        git_folder = (ctx.fs.link_target(repository) or repository) / ".git"
        return [why for delete in found for why in self.refusals(delete, roots, git_folder, host, ctx)], roots

    @staticmethod
    def repository(event: Event, ctx: Context) -> Path:
        """The top of the git repository holding the working folder, or the folder itself outside git."""
        try:
            return ctx.git.root(event.cwd) or event.cwd
        except GitError:
            return event.cwd

    def roots(self, repository: Path, event: Event, ctx: Context) -> list[Path]:
        """The allowed roots, each as its real path."""
        home = (ctx.env.get("USERPROFILE") or ctx.env.get("HOME") or "~").replace("\\", "/")
        configured = (paths.normalise(re.sub(r"^~(?=$|[/\\])", home, str(root)), repository, ctx.platform)
                      for root in self.options.get("roots", []))
        named = [repository, event.scratchpad, *paths.temp_folders(ctx.platform, ctx.env), *configured]
        return [ctx.fs.link_target(root) or root for root in named if root is not None]

    def refusals(self, delete: Delete, roots: list[Path], git_folder: Path, host: Host,
                 ctx: Context) -> list[str]:
        """Why each path the delete names is refused, one line per refused path. A path the system rejects,
        such as one too long or with a character Windows refuses, is refused with the system's words."""
        try:
            resolved = resolve(delete, host)
            if resolved.unresolved:
                return [f"{delete.how} {delete.target or '(no path)'}: {resolved.unresolved}"]
            return [f"{delete.how} {path.as_posix()}: {why}" for path in resolved.paths
                    if (why := self.refusal(delete, path, resolved.globbed, roots, git_folder, ctx))]
        except (OSError, ValueError) as error:
            return [f"{delete.how} {delete.target}: io-guard could not resolve it: {error}"]

    @staticmethod
    def refusal(delete: Delete, path: Path, globbed: bool, roots: list[Path], git_folder: Path,
                ctx: Context) -> str | None:
        """Why deleting path is refused, or None when it is allowed."""
        real = ctx.fs.link_target(path) or path
        through = "" if real == path else f", through a link to {real.as_posix()}"
        if paths.inside(real, roots, ctx.platform) is None:
            return f"it is outside the allowed folders{through}"
        in_git = paths.inside(real, [git_folder], ctx.platform) is not None
        if in_git and (delete.recursive or globbed):
            return f"it is the repository's .git folder or inside it{through}"
        if not delete.recursive:
            return None
        held = [root for root in roots if paths.inside(root, [real], ctx.platform) is not None]
        if any(paths.inside(real, [root], ctx.platform) is not None for root in held):
            return f"it is an allowed folder itself{through}"
        if held:
            return f"it holds an allowed folder{through}"
        return None

    def result(self, refused: list[str], roots: list[Path], event: Event, ctx: Context) -> Result:
        shown = max(1, int(self.options.get("shown", 5)))
        listed = "; ".join(refused[:shown])
        more = f"; and {len(refused) - shown} more" if len(refused) > shown else ""
        allowed = ", ".join(root.as_posix() for root in roots)
        message = (f"This command deletes what io-guard does not allow: {listed}{more}. A delete stays "
                   f"inside {allowed}, never removes one of them or the repository's .git whole, and names "
                   "each path literally.")
        return Result.of(Code.SHELL_DELETE, message, event.tool_name, ctx.platform.os,
                         evidence={"refused": refused, "roots": [root.as_posix() for root in roots]},
                         fix=Fix(event.tool_name, {}, "Name each path to delete literally, inside those "
                                                      "folders, or ask the user to run the command."))
