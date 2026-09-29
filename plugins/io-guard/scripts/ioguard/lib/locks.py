"""The processes that hold a file open, and a lock that io-guard's own processes share on one file.

A tool's write replaces a file by renaming a temporary file over it, and Windows refuses the rename with EPERM
while another process holds the file without FILE_SHARE_DELETE, such as an editor or a build. The Restart
Manager is the Windows API for that question, reached through ctypes. macOS asks lsof, whose -F pc output
gives a process id line and a command line per holder.

file_lock serialises io-guard's processes, two sessions' servers or a server and a command hook, on one path.
It locks a file named for the path in io-guard's folder, never the path itself, so no editor or build
ever waits on it. A waiter waits in the kernel, never by polling, so a release reaches it before the holder
can take the lock again: LockFileEx on Windows, and flock in a helper thread on macOS. A holder that dies
loses the lock with its handle.
"""
import functools
import hashlib
import os
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ioguard.lib import paths, proc
from ioguard.lib.platform import Platform

MORE_DATA = 234          # ERROR_MORE_DATA: the list grew between the two RmGetList calls
ATTEMPTS = 3
GENERIC_READ_WRITE = 0x80000000 | 0x40000000
SHARE_ALL = 0x1 | 0x2 | 0x4              # read, write and delete
OPEN_ALWAYS = 4
FILE_FLAG_OVERLAPPED = 0x40000000
LOCKFILE_EXCLUSIVE_LOCK = 0x2
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
INVALID_HANDLE = 2 ** (64 if sys.maxsize > 2 ** 32 else 32) - 1


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
    block. TimeoutError when another holder keeps it past wait_s seconds. 0 takes it only if it is free."""
    folder = data_dir / "locks"
    folder.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(paths.resolved(path).encode("utf-8")).hexdigest()
    take = windows_lock if sys.platform == "win32" else posix_lock
    try:
        release = take(folder / f"{name}.lock", wait_s)
    except TimeoutError:
        raise TimeoutError(f"Another io-guard process has held {path} for {wait_s:g} seconds.") from None
    try:
        yield
    finally:
        release()


@functools.cache
def kernel32() -> Any:
    """kernel32 with the prototypes windows_lock calls, loaded once."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    overlapped = ctypes.POINTER(overlapped_type())
    for name, restype, argtypes in (
            ("CreateFileW", wintypes.HANDLE, (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                               wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                               wintypes.HANDLE)),
            ("CreateEventW", wintypes.HANDLE, (wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL,
                                               wintypes.LPCWSTR)),
            ("LockFileEx", wintypes.BOOL, (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                           wintypes.DWORD, overlapped)),
            ("UnlockFileEx", wintypes.BOOL, (wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                             overlapped)),
            ("WaitForSingleObject", wintypes.DWORD, (wintypes.HANDLE, wintypes.DWORD)),
            ("CancelIoEx", wintypes.BOOL, (wintypes.HANDLE, overlapped)),
            ("GetOverlappedResult", wintypes.BOOL, (wintypes.HANDLE, overlapped,
                                                    ctypes.POINTER(wintypes.DWORD), wintypes.BOOL)),
            ("CloseHandle", wintypes.BOOL, (wintypes.HANDLE,))):
        function = getattr(kernel, name)
        function.restype, function.argtypes = restype, argtypes
    return kernel


@functools.cache
def overlapped_type() -> type:
    """The OVERLAPPED structure, which carries the lock's offset and the event its wait ends on."""
    import ctypes
    from ctypes import wintypes

    class Structure(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]
    return Structure


def windows_lock(lock_file: Path, wait_s: float) -> Callable[[], None]:
    """Take the lock file's first byte, waiting in the kernel up to wait_s. Windows grants a released byte
    range to its waiters in the order they asked. The function that lets it go."""
    import ctypes
    from ctypes import wintypes
    kernel = kernel32()
    handle = kernel.CreateFileW(str(lock_file), GENERIC_READ_WRITE, SHARE_ALL, None, OPEN_ALWAYS,
                                FILE_FLAG_OVERLAPPED, None)
    if handle in (None, INVALID_HANDLE):
        raise ctypes.WinError(ctypes.get_last_error())
    event = kernel.CreateEventW(None, True, False, None)
    request, done = overlapped_type()(hEvent=event), wintypes.DWORD()

    def close() -> None:
        kernel.CloseHandle(event)
        kernel.CloseHandle(handle)

    def release() -> None:
        kernel.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(overlapped_type()()))
        close()
    try:
        if kernel.LockFileEx(handle, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, ctypes.byref(request)):
            return release
        if ctypes.get_last_error() != ERROR_IO_PENDING:
            raise ctypes.WinError(ctypes.get_last_error())
        if kernel.WaitForSingleObject(event, max(0, round(wait_s * 1000))) != WAIT_OBJECT_0:
            kernel.CancelIoEx(handle, ctypes.byref(request))
            if kernel.GetOverlappedResult(handle, ctypes.byref(request), ctypes.byref(done), True):
                kernel.UnlockFileEx(handle, 0, 1, 0, ctypes.byref(overlapped_type()()))
            raise TimeoutError
        if not kernel.GetOverlappedResult(handle, ctypes.byref(request), ctypes.byref(done), False):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        close()
        raise
    return release


class PosixWait:
    """A blocking flock in a helper thread, which the caller gives up on at its timeout. A lock that lands
    after that is let go at once, and the thread closes the descriptor, since only it still uses it."""

    def __init__(self, fd: int) -> None:
        self.fd, self.state, self.got, self.gave_up = fd, threading.Lock(), threading.Event(), False

    def wait(self) -> None:
        import fcntl
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX)
        except OSError:
            with self.state:
                self.gave_up = True
            os.close(self.fd)
            return
        with self.state:
            if not self.gave_up:
                self.got.set()
                return
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)

    def give_up(self) -> bool:
        """True when the lock had not landed and never will for this caller, False when it just did."""
        with self.state:
            if self.got.is_set():
                return False
            self.gave_up = True
            return True


def posix_lock(lock_file: Path, wait_s: float) -> Callable[[], None]:
    """Take the lock file with flock, waiting in the kernel up to wait_s. A released lock wakes its waiters,
    which take it again in the kernel. The function that lets it go."""
    import fcntl
    fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o644)

    def release() -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return release
    except BlockingIOError:
        pass
    except BaseException:
        os.close(fd)
        raise
    waiter = PosixWait(fd)
    threading.Thread(target=waiter.wait, name="io-guard lock wait", daemon=True).start()
    if waiter.got.wait(wait_s) or not waiter.give_up():
        return release
    raise TimeoutError
