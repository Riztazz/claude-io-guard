"""Paths as the agent names them, turned into one absolute form, the arguments Git Bash rewrites as paths,
and a thread lock per file."""
import ntpath
import os
import posixpath
import re
import threading
import unicodedata
from collections.abc import Collection
from pathlib import Path

from ioguard.lib.platform import Platform, detect

SLASH_ARGUMENT = re.compile(r"^(--?[\w-]+[=:])?(/(?!/)[^/;]*)(/)?")
DEVICE_NAMES = frozenset({"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)),
                          *(f"lpt{n}" for n in range(1, 10))})


def normalise(raw: str, cwd: Path, platform: Platform) -> Path:
    """The absolute path raw names, relative to cwd, with . and .. folded and no link followed.

    A Windows path comes back with forward slashes, which a Windows Path reads as it reads backslashes, so a
    test that reads an event as Windows on a macOS host still gets a path made of its parts. On macOS each
    name is NFC, the form a user types, because the file system may hand back NFD.
    """
    module = ntpath if platform.windows else posixpath
    folded = module.normpath(module.join(str(cwd), raw))
    if platform.windows:
        folded = folded.replace("\\", "/")
    if platform.macos:
        folded = unicodedata.normalize("NFC", folded)
    return Path(folded)


def shown(path: Path, cwd: Path, scratchpad: Path | None = None) -> str:
    """path as a message names it: from cwd when under it, from the session's scratchpad as scratchpad/...
    when under that, whole otherwise, and cwd itself in words."""
    try:
        relative = path.relative_to(cwd).as_posix()
    except ValueError:
        if scratchpad is not None and path.is_relative_to(scratchpad):
            return f"scratchpad/{path.relative_to(scratchpad).as_posix()}"
        return path.as_posix()
    return "the current folder" if relative == "." else relative


def reserved(path: Path) -> str | None:
    """The Windows device name path's file name stands for, such as nul for nul.txt, or None. Windows reads
    the name before the first dot, trailing spaces dropped, without case."""
    stem = path.name.split(".", 1)[0].rstrip(" ").lower()
    return stem if stem in DEVICE_NAMES else None


def link_target(path: Path) -> Path | None:
    """Where path really is when it, or a folder above it, is a junction or a symbolic link, or None. A path
    that does not exist yet resolves through the folders that do."""
    real = os.path.realpath(path)
    return None if os.path.normcase(real) == os.path.normcase(os.path.abspath(path)) else Path(real)


def resolved(path: Path, platform: Platform | None = None) -> str:
    """One name per file for path: absolute, through every junction and link, NFC on macOS, and with case
    folded where the file system ignores it, so two spellings of one file give one name."""
    on = platform or detect()
    real = os.path.realpath(path)
    if on.windows:
        real = os.path.normcase(real)
    if on.macos:
        real = unicodedata.normalize("NFC", real)
    return real.casefold() if on.case_insensitive else real


class LockTable:
    """One thread lock per file, by its resolved path, so two of a process's threads that change one file
    take turns. The table keeps each lock for the life of the process."""

    def __init__(self) -> None:
        self.locks: dict[str, threading.Lock] = {}
        self.guard = threading.Lock()

    def lock(self, path: Path) -> threading.Lock:
        with self.guard:
            return self.locks.setdefault(resolved(path), threading.Lock())


def inside(path: Path, roots: Collection[Path], platform: Platform) -> Path | None:
    """The deepest of roots that holds path, or None. Names compare without case where the platform's file
    system ignores it. Both sides come from normalise, so neither has a . or .. left."""
    def parts(of: Path) -> tuple[str, ...]:
        return tuple(part.casefold() for part in of.parts) if platform.case_insensitive else of.parts
    held = parts(path)
    holding = [root for root in roots if held[:len(parts(root))] == parts(root)]
    return max(holding, key=lambda root: len(root.parts), default=None)


def msys_prefix(word: str, posix_roots: Collection[str]) -> str | None:
    """The prefix that keeps Git Bash from converting word when it passes word to a Windows program, or None
    when the conversion is wanted or never happens.

    Git Bash rewrites an argument that starts with a slash, or an --option= followed by one, into a Windows
    path under its own install folder, and a lone /F into the drive F:/. A drive with a path after it, such as
    /c/Users, and the roots in posix_roots are paths meant for that rewrite. Any other first segment, such as
    /Game/, /PID or the switch /F, is a name the program expects as written. A doubled slash already escapes
    the rewrite."""
    match = SLASH_ARGUMENT.match(word)
    if match is None:
        return None
    head, segment, slash = match[1] or "", match[2], match[3] or ""
    name = segment[1:]
    drive = re.fullmatch(r"[A-Za-z]", name) and slash
    if not name or drive or name.lower() in posix_roots:
        return None
    return head + segment + slash
