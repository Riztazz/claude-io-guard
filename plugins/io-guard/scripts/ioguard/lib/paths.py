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

    On macOS each name is NFC, the form a user types, because the file system may hand back NFD.
    """
    module = ntpath if platform.windows else posixpath
    joined = module.join(str(cwd), raw)
    folded = module.normpath(joined)
    if platform.macos:
        folded = unicodedata.normalize("NFC", folded)
    return Path(folded)
