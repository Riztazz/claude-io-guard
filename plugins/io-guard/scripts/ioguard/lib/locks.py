"""The processes that hold a file open, and a lock that io-guard's own processes share on one file.

A tool's write replaces a file by renaming a temporary file over it, and Windows refuses the rename with EPERM
while another process holds the file without FILE_SHARE_DELETE, such as an editor or a build. The Restart
Manager is the Windows API for that question, reached through ctypes. macOS asks lsof, whose -F pc output
gives a process id line and a command line per holder.

file_lock serialises io-guard's processes, two sessions' servers or a server and a command hook, on one path.
It locks a file named for the path in io-guard's folder, never the path itself, so no editor or build
ever waits on it.
"""
import hashlib
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ioguard.lib import paths, proc
from ioguard.lib.platform import Platform

MORE_DATA = 234          # ERROR_MORE_DATA: the list grew between the two RmGetList calls
ATTEMPTS = 3
RETRY_S = 0.02


@dataclass(frozen=True)
class Process:
    pid: int
    name: str


def holders(path: Path, platform: Platform) -> tuple[Process, ...]:
    """The processes holding path open. OSError when the platform's API or tool cannot answer."""
    if platform.windows:
        return restart_manager(path)
    done = proc.run(["lsof", "-F", "pc", "--", str(path)], path.parent, timeout_s=5.0)
    if done.start_error or done.timed_out:
        raise OSError(f"lsof could not answer for {path}: {done.start_error or 'timed out'}")
    return parse_lsof(done.stdout)


def parse_lsof(raw: bytes) -> tuple[Process, ...]:
    """lsof -F pc output: a p line with the process id, then a c line with its command, per process."""
    found, pid = [], None
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("c") and pid is not None:
            found.append(Process(pid, line[1:]))
            pid = None
    return tuple(found)


def restart_manager(path: Path) -> tuple[Process, ...]:
    """The Restart Manager's list of processes that use path."""
    if sys.platform != "win32":
        raise OSError("The Restart Manager exists on Windows only.")
    import ctypes
    from ctypes import wintypes

    class UniqueProcess(ctypes.Structure):
        _fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", wintypes.FILETIME)]

    class ProcessInfo(ctypes.Structure):
        _fields_ = [("Process", UniqueProcess), ("strAppName", wintypes.WCHAR * 256),
                    ("strServiceShortName", wintypes.WCHAR * 64), ("ApplicationType", ctypes.c_int),
                    ("AppStatus", wintypes.ULONG), ("TSSessionId", wintypes.DWORD),
                    ("bRestartable", wintypes.BOOL)]

    manager = ctypes.WinDLL("rstrtmgr")
    session, key = wintypes.DWORD(), ctypes.create_unicode_buffer(33)
    if manager.RmStartSession(ctypes.byref(session), 0, key):
        raise OSError("RmStartSession failed.")
    try:
        files = (wintypes.LPCWSTR * 1)(str(path))
        if manager.RmRegisterResources(session, 1, files, 0, None, 0, None):
            raise OSError(f"RmRegisterResources failed for {path}.")
        needed, reasons = wintypes.UINT(0), wintypes.DWORD(0)
        for _ in range(ATTEMPTS):
            count = wintypes.UINT(needed.value)
            infos = (ProcessInfo * max(needed.value, 1))()
            result = manager.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), infos,
                                       ctypes.byref(reasons))
            if result == 0:
                return tuple(Process(info.Process.dwProcessId, info.strAppName)
                             for info in infos[:count.value])
            if result != MORE_DATA:
                raise OSError(f"RmGetList failed with {result} for {path}.")
        raise OSError(f"The list of processes that hold {path} kept growing.")
    finally:
        manager.RmEndSession(session)


@contextmanager
def file_lock(path: Path, data_dir: Path, wait_s: float = 5.0) -> Iterator[None]:
    """Hold path against every other io-guard process and thread that asks for the same path, for the with
    block. TimeoutError when another holder keeps it past wait_s seconds."""
    folder = data_dir / "locks"
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(paths.resolved(path).encode("utf-8")).hexdigest()
    deadline = time.monotonic() + wait_s
    with open(folder / f"{name}.lock", "a+b") as handle:
        while not locked(handle):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Another io-guard process has held {path} for {wait_s:g} seconds.")
            time.sleep(RETRY_S)
        try:
            yield
        finally:
            unlocked(handle)


def locked(handle: BinaryIO) -> bool:
    """Take the lock file's lock without waiting: its first byte on Windows, the whole file on macOS."""
    try:
        if sys.platform == "win32":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def unlocked(handle: BinaryIO) -> None:
    if sys.platform == "win32":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
