"""Where things are: Claude Code's folder, io-guard's folder, a session's shared files, and the project and
the repository a path belongs to.
"""
from collections.abc import Mapping
from pathlib import Path

from ioguard.lib.git import GitError
from ioguard.lib.ports import GitPort


def claude_folder(env: Mapping[str, str]) -> Path:
    """Claude Code's own folder: CLAUDE_CONFIG_DIR, then .claude in the home folder env names, USERPROFILE
    or HOME, then in the process's own home folder."""
    if env.get("CLAUDE_CONFIG_DIR"):
        return Path(env["CLAUDE_CONFIG_DIR"])
    home = env.get("USERPROFILE") or env.get("HOME")
    return (Path(home) if home else Path.home()) / ".claude"


def home_folder(env: Mapping[str, str]) -> Path:
    """io-guard's folder, which every copy of the plugin on the machine shares, whatever id Claude Code gives
    it: IOGUARD_HOME, then io-guard in Claude Code's own folder. It holds the user's config.json, the file
    locks, the telemetry and the session files."""
    return Path(env["IOGUARD_HOME"]) if env.get("IOGUARD_HOME") else claude_folder(env) / "io-guard"


def session_file(data_dir: Path, session_id: str, kind: str) -> Path:
    """A file the session's io-guard processes share: sessions/<session>.<kind> in io-guard's folder."""
    return data_dir / "sessions" / f"{session_id}.{kind}"


def memory_file(path: Path, env: Mapping[str, str]) -> bool:
    """Whether path is a note of Claude Code's memory, projects/<project>/memory/<name>.md in its folder,
    whose frontmatter the desktop app rewrites after every write (context.md, "Hooks and MCP", row 39)."""
    try:
        parts = path.relative_to(claude_folder(env) / "projects").parts
    except ValueError:
        return False
    return len(parts) == 3 and parts[1] == "memory" and path.suffix.lower() == ".md"


def project_root(cwd: Path) -> Path:
    """The project a working folder belongs to: the nearest folder at or above it that holds io-guard's
    project config, else the nearest that holds .git, else the folder itself."""
    for folder in (cwd, *cwd.parents):
        claude = folder / ".claude"
        if (claude / "io-guard.json").is_file() or (claude / "io-guard.local.json").is_file():
            return folder
        if (folder / ".git").exists():
            return folder
    return cwd


def project_of(env: Mapping[str, str], fallback: Path) -> Path:
    """The folder whose .claude settings Claude Code reads: CLAUDE_PROJECT_DIR, else fallback."""
    named = env.get("CLAUDE_PROJECT_DIR")
    return Path(named) if named else fallback


def repository_root(git: GitPort, path: Path) -> Path | None:
    """The repository that holds path, or None outside one or when git cannot say."""
    try:
        return git.root(path)
    except GitError:
        return None
