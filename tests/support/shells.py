"""The shells the tests run commands in: the bash and sh Claude Code's Bash tool runs.

On Windows that is Git Bash, never the bash.exe in System32, which starts WSL, or its WindowsApps alias. A
test run from PowerShell or cmd.exe has no Git Bash on its PATH, so the one beside git's install stands in.
"""
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from ioguard.lib import proc
from ioguard.lib.probing import ToolVersion
from ioguard.lib.runs import NOT_BASH


def git_folder() -> Path | None:
    """Git for Windows' install folder, from the git on PATH: <folder>/cmd/git.exe, <folder>/bin/git.exe, or
    <folder>/mingw64/bin/git.exe, which Git Bash's own PATH finds first."""
    git = proc.on_path("git", os.environ)
    if git is None:
        return None
    folder = Path(git).resolve().parents[1]
    return folder.parent if folder.name.lower() == "mingw64" else folder


def without_git_tools(env: Mapping[str, str]) -> dict[str, str]:
    """env with every folder of Git's install taken off PATH but its cmd folder, as the Windows PATH Claude
    Code gives io-guard's server has it."""
    key = next(name for name in env if name.upper() == "PATH")
    inside = str(git_folder()).lower()
    kept = [entry for entry in env[key].split(";")
            if not entry.lower().startswith(inside) or entry.lower().endswith("cmd")]
    return {**env, key: ";".join(kept)}


def git_bash() -> ToolVersion:
    """Git's own bash, as the session probe saves it."""
    return ToolVersion(str(git_folder() / "usr" / "bin" / "bash.exe"), "5.2")


def windows_shell(name: str) -> str | None:
    found = proc.on_path(name, os.environ, NOT_BASH)
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
