"""Paths as the agent names them, turned into one absolute form, and the arguments Git Bash rewrites as
paths."""
import ntpath
import os
import posixpath
import re
import unicodedata
from collections.abc import Collection
from pathlib import Path

from ioguard.lib.platform import Platform

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
