"""Paths as the agent names them, turned into one absolute form.

Task 14 adds reserved names, links and write roots.
"""
import ntpath
import posixpath
import unicodedata
from pathlib import Path

from ioguard.lib.platform import Platform


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
