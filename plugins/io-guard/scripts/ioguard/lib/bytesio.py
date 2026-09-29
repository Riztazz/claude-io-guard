"""Files as bytes: one reader, and the one writer every io-guard write goes through.

write_atomic writes a temporary file beside the target and renames it over the target, so a reader sees
the old bytes or the new ones and never half a file. open(path, "w") truncates first, which is how a file
ends up empty.
"""
import errno
import os
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WriteReport:
    path: Path
    bytes_written: int
    attempts: int


def regular(path: Path) -> Path:
    """path, when it names a regular file. OSError otherwise: a device such as CON or /dev/zero, a pipe, or a
    folder, which a read would block on, read without end, or fail on."""
    if not stat.S_ISREG(os.stat(path).st_mode):
        raise OSError(errno.EINVAL, "not a regular file", str(path))
    return path


def read_bytes(path: Path, limit: int | None = None) -> bytes:
    """The file's bytes, or its first limit bytes."""
    with open(regular(path), "rb") as source:
        return source.read() if limit is None else source.read(limit)


def read_from(path: Path, offset: int, limit: int) -> bytes:
    """Up to limit bytes of the file from byte offset on."""
    with open(regular(path), "rb") as source:
        source.seek(offset)
        return source.read(limit)


def read_tail(path: Path, limit: int) -> bytes:
    """The file's last limit bytes, from the first line break in them when the file is longer, so every line
    in the result is whole."""
    with open(regular(path), "rb") as source:
        size = source.seek(0, os.SEEK_END)
        source.seek(max(0, size - limit))
        data = source.read()
    if size <= limit:
        return data
    cut = data.find(b"\n")
    return data[cut + 1:] if cut >= 0 else b""


def write_atomic(path: Path, data: bytes, retries: int = 5) -> WriteReport:
    """Write data to path through a temporary file in the same folder and a rename.

    On Windows a rename fails with PermissionError while another process holds the target, such as a virus
    scanner or an editor. The rename is retried with a growing wait, and the last failure is raised. A path
    that is a symlink is written at the file it points to, so the link stays. On macOS the new file takes the
    old one's mode, since mkstemp makes it 0600.
    """
    report_path = path
    if path.is_symlink():
        path = Path(os.path.realpath(path))
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode) if os.name == "posix" else None
    except FileNotFoundError:
        mode = None
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".ioguard-tmp", dir=path.parent)
    try:
        if mode is not None:
            os.chmod(temporary, mode)
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        attempt = 1
        while True:
            try:
                os.replace(temporary, path)
                return WriteReport(path=report_path, bytes_written=len(data), attempts=attempt)
            except PermissionError:
                if attempt >= retries:
                    raise
                time.sleep(0.02 * 2 ** attempt)
                attempt += 1
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
