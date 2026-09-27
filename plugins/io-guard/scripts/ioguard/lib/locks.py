"""The processes that hold a file open: the Restart Manager on Windows, lsof on macOS.

A tool's write replaces a file by renaming a temporary file over it, and Windows refuses the rename with EPERM
while another process holds the file without FILE_SHARE_DELETE, such as an editor or a build. The Restart
Manager is the Windows API for that question, reached through ctypes. macOS asks lsof, whose -F pc output
gives a process id line and a command line per holder.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

from ioguard.lib import proc
from ioguard.lib.platform import Platform

MORE_DATA = 234          # ERROR_MORE_DATA: the list grew between the two RmGetList calls
ATTEMPTS = 3


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
