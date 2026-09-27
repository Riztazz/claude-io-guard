"""Files as bytes: one reader, and the one writer every io-guard write goes through.

write_atomic writes a temporary file beside the target and renames it over the target, so a reader sees
the old bytes or the new ones and never half a file. open(path, "w") truncates first, which is how a file
ends up empty.
"""
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteReport:
    path: Path
    bytes_written: int
    attempts: int


def read_bytes(path: Path, limit: int | None = None) -> bytes:
    """The file's bytes, or its first limit bytes."""
    with open(path, "rb") as source:
        return source.read() if limit is None else source.read(limit)


def write_atomic(path: Path, data: bytes, retries: int = 5) -> WriteReport:
    """Write data to path through a temporary file in the same folder and a rename.

    On Windows a rename fails with PermissionError while another process holds the target, such as a virus
    scanner or an editor. The rename is retried with a growing wait, and the last failure is raised.
    """
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".ioguard-tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        attempt = 1
        while True:
            try:
                os.replace(temporary, path)
                return WriteReport(path=path, bytes_written=len(data), attempts=attempt)
            except PermissionError:
                if attempt >= retries:
                    raise
                time.sleep(0.02 * 2 ** attempt)
                attempt += 1
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
