"""The pre-commit check: each staged text file against its last commit, through verify.write's comparison.

A commit carries the bytes git stores, so the check compares HEAD's blob with the staged one, never the
working tree. It reports what the staged change did to a file that no commit should carry unnoticed (GIT-9):
a changed ending style or BOM, bytes that stop being UTF-8 or gain U+FFFD, new control bytes, non-ASCII in a
file the project keeps ASCII, a new character the Read tool shows as nothing, and a new indent style. A file
new to the commit is checked for its odd bytes only, and a binary file is skipped. verify.write's ascii_only
and invisible_allowed come from the project's io-guard.json and from the user's config.json in
io-guard's folder.
"""
from collections.abc import Mapping
from pathlib import Path

from ioguard.checks.registry import default_registry
from ioguard.lib.compare import Written, ascii_kept, compare
from ioguard.lib.context import Context, GitPort, home_folder
from ioguard.lib.drift import text_of
from ioguard.lib.git import Git, GitError
from ioguard.lib.platform import Platform
from ioguard.lib.profile import profile
from ioguard.lib.results import Result

WHAT = "The staged change"


def staged_results(root: Path, git: GitPort, ascii_only: list[str], platform: Platform,
                   allowed: frozenset[str] = frozenset()) -> tuple[Result, ...]:
    """What each staged text file's change did to its bytes, as warnings. allowed names the invisible
    characters a change may add."""
    found: list[Result] = []
    for name in git.staged(root):
        after = git.blob(root, f":{name}")
        before = git.blob(root, f"HEAD:{name}")
        if after is None or profile(after if before is None else before).binary:
            continue
        path = root / name
        written = Written(path, WHAT, None if before is None else profile(before),
                          None if before is None else text_of(before), after, None,
                          ascii_kept(path, ascii_only), allowed)
        found.extend(compare(written, "git", platform.os, collapse_percent=0))
    return tuple(found)


def report(root: Path, results: tuple[Result, ...]) -> str:
    """One line per finding, the file first, then what to do."""
    lines = [f"{result.file.relative_to(root).as_posix()}: {result.render()}" for result in results]
    lines.append(f"io-guard found {len(results)} problem{'' if len(results) == 1 else 's'} in the staged "
                 f"files. Fix them and stage the files again, or skip this check with git commit "
                 f"--no-verify.")
    return "\n".join(lines)


def run(cwd: Path, env: Mapping[str, str]) -> tuple[int, str]:
    """The exit code and the text for the repository that holds cwd: 1 and the findings when there are any."""
    try:
        root = Git().root(cwd)
        if root is None:
            return 1, "io-guard's pre-commit check runs inside a git repository."
        ctx = Context.live(home_folder(env), root, default_registry().keys())
        results = staged_results(root, ctx.git, ctx.config.check_options("verify.write")["ascii_only"],
                                 ctx.platform, frozenset(ctx.config.get("invisible_allowed")))
    except GitError as error:
        return 1, f"io-guard's pre-commit check could not read the staged files: {error}"
    notice = ctx.config_report.user_message if ctx.config_report else None
    text = "\n".join(part for part in (notice, report(root, results) if results else None) if part)
    return (1 if results else 0), text
