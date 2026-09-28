"""The shells the tests run commands in: the bash and sh Claude Code's Bash tool runs.

On Windows that is Git Bash, never the bash.exe in System32, which starts WSL, or its WindowsApps alias. A
test run from PowerShell or cmd.exe has no Git Bash on its PATH, so the one beside git's install stands in.
"""
import os
import shutil
import sys
from pathlib import Path

from ioguard.checks.session_probe import NOT_BASH
from ioguard.lib import probing


def git_folder() -> Path | None:
    """Git for Windows' install folder, from the git on PATH: <folder>/cmd/git.exe or <folder>/bin/git.exe."""
    git = probing.find("git", os.environ)
    return None if git is None else Path(git).resolve().parents[1]


def windows_shell(name: str) -> str | None:
    found = probing.find(name, os.environ, NOT_BASH)
    if found:
        return found
    folder = git_folder()
    beside = None if folder is None else folder / "bin" / f"{name}.exe"
    return str(beside) if beside is not None and beside.is_file() else None


def bash() -> str | None:
    """The bash to run a test's command in, or None when the machine has none."""
    if sys.platform != "win32":
        return shutil.which("bash")
    return os.environ.get("CLAUDE_CODE_GIT_BASH_PATH") or windows_shell("bash")


def sh() -> str | None:
    """The sh a command hook runs pyrun in, or bash when there is no sh, or None when there is neither."""
    if sys.platform != "win32":
        return shutil.which("sh") or shutil.which("bash")
    return windows_shell("sh") or bash()
