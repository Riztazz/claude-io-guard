"""Deleting what io-guard keeps past its time: a folder's entries whose newest file is older than a cutoff.

io-guard's folder keeps whole tool results, io.run's bodies and logs, and the command bodies transport.body
moves into files, and each can hold a project's content. The io server deletes the old ones at its start.
"""
import logging
import shutil
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

log = logging.getLogger("ioguard.lib")


def newest(entry: Path) -> float:
    """The latest modification time of a file, or of the files under a folder, or of the folder itself when
    it holds none."""
    files = [path for path in entry.rglob("*") if path.is_file()] if entry.is_dir() else [entry]
    return max((path.stat().st_mtime for path in files), default=entry.stat().st_mtime)


def older(folder: Path, cutoff: datetime) -> list[Path]:
    """The files and folders directly in folder whose newest file changed before cutoff, and an empty list
    when folder does not exist."""
    if not folder.is_dir():
        return []
    return sorted(entry for entry in folder.iterdir() if newest(entry) < cutoff.timestamp())


def delete(paths: Iterable[Path]) -> list[Path]:
    """Delete each file or folder. One another process holds open stays, and the log names it. The paths
    deleted."""
    gone = []
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            gone.append(path)
        except OSError as failure:
            log.warning("io-guard could not delete %s: %s", path, failure)
    return gone
