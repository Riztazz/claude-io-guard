"""Running a program from an argument list, with no shell: to the end with a timeout, or in the background
with its output going to a log.

A program named without a folder starts only from an absolute folder on the environment's PATH, found by
on_path and started by its full path, and one PATH does not hold does not start. Windows' CreateProcess and
Python's shutil.which both search the current folder first unless NoDefaultCurrentDirectoryInExePath is set,
and macOS reads an empty or relative PATH entry as the current folder, which is the user's project.

A background program starts in its own process group, so stopping it stops what it started too: taskkill /T
on Windows, and a signal to the group on macOS. Its stdin is empty, because nothing would ever answer a
prompt, and its stdout and stderr go to one log in the order the program flushes them, through lib.logcap,
which stops the log at a cap and lets the program go on.
"""
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunResult:
    argv: tuple[str, ...]
    exit_code: int | None        # None when the program timed out or could not start
    stdout: bytes
    stderr: bytes
    timed_out: bool
    duration_s: float
    start_error: str | None = None   # why the program could not start, such as a missing executable

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


WINDOWS_EXTENSIONS = ".COM;.EXE;.BAT;.CMD"        # PATHEXT's default
LOGCAP = Path(__file__).with_name("logcap.py")     # the copier a background run's output goes through
COPIER_WAIT_S = 10.0     # seconds the copier may take to write the last output once the program has ended


def names_of(name: str, env: Mapping[str, str]) -> list[str]:
    """The file names a program name stands for: itself, or on Windows itself with each PATHEXT extension when
    it has none of them."""
    if sys.platform != "win32":
        return [name]
    extensions = [each for each in env.get("PATHEXT", WINDOWS_EXTENSIONS).split(";") if each]
    return [name] if any(name.lower().endswith(each.lower()) for each in extensions) else \
        [name + each for each in extensions]


def on_path(name: str, env: Mapping[str, str], skip: Sequence[str] = ()) -> str | None:
    """The full path of the first file name stands for in an absolute folder on the environment's PATH whose
    folder names none of skip, ignoring case, or None. The current folder is never searched: an empty or
    relative entry is passed over, and shutil.which is not used, since on Windows it looks there first."""
    for folder in env.get("PATH", "").split(os.pathsep):
        if not os.path.isabs(folder) or any(part.lower() in folder.lower() for part in skip):
            continue
        for each in names_of(name, env):
            path = os.path.join(folder, each)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return path
    return None


def located(argv: Sequence[str], env: Mapping[str, str] | None) -> tuple[str, ...] | None:
    """argv with a program named without a folder replaced by where PATH holds it, a program given as a path
    as it is, or None when PATH holds no such program. env None is this process's environment."""
    name = argv[0]
    if Path(name).name != name:
        return tuple(argv)
    found = on_path(name, os.environ if env is None else env)
    return None if found is None else (found, *argv[1:])


def not_on_path(name: str) -> str:
    return f"{name} is not on PATH, so io-guard did not start it."


def run(argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None,
        timeout_s: float = 10.0, stdin: bytes = b"") -> RunResult:
    """Run argv in cwd with stdin as its input, and wait. A timeout, a program PATH does not hold, or one that
    cannot start, is a result, not a raise. The program never reads the caller's own stdin, which in the io
    server is the client's messages."""
    started = time.monotonic()
    command = tuple(argv)
    resolved = located(command, env)
    if resolved is None:
        return RunResult(command, None, b"", b"", False, 0.0, start_error=not_on_path(command[0]))
    try:
        done = subprocess.run(resolved, cwd=cwd, env=None if env is None else dict(env), capture_output=True,
                              input=stdin, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired as expired:
        return RunResult(command, None, expired.stdout or b"", expired.stderr or b"", True,
                         time.monotonic() - started)
    except OSError as error:
        return RunResult(command, None, b"", b"", False, time.monotonic() - started, start_error=str(error))
    return RunResult(command, done.returncode, done.stdout, done.stderr, False, time.monotonic() - started)


class Pump:
    """A program running with its output going to a log, and the moment it ended. A thread waits on the
    process, and on the copier that writes its log, so ended is set even when nobody asks, and only once the
    log holds the last of the output."""

    def __init__(self, process: subprocess.Popen, argv: tuple[str, ...], log: Path,
                 copier: subprocess.Popen | None = None) -> None:
        self.process, self.argv, self.log, self.copier = process, argv, log, copier
        self.started = time.monotonic()
        self.ended: float | None = None
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.callbacks: list[Callable[[], None]] = []
        threading.Thread(target=self.watch, name="io-guard run", daemon=True).start()

    def watch(self) -> None:
        self.process.wait()
        if self.copier is not None:
            try:
                self.copier.wait(COPIER_WAIT_S)
            except subprocess.TimeoutExpired:
                self.copier.kill()
        with self.lock:
            self.ended = time.monotonic()
            self.done.set()
            callbacks, self.callbacks = self.callbacks, []
        for callback in callbacks:
            callback()

    def when_done(self, callback: Callable[[], None]) -> None:
        """Call callback when the program ends, or now when it has."""
        with self.lock:
            if not self.done.is_set():
                self.callbacks.append(callback)
                return
        callback()

    @property
    def exit_code(self) -> int | None:
        return self.process.returncode if self.done.is_set() else None

    def wait(self, timeout_s: float) -> bool:
        """True when the program ended within timeout_s seconds."""
        return self.done.wait(timeout_s)

    def seconds(self) -> float:
        return (self.ended if self.ended is not None else time.monotonic()) - self.started

    def stop(self) -> None:
        """End the program and everything it started."""
        if self.done.is_set():
            return
        if sys.platform == "win32":
            run(["taskkill", "/T", "/F", "/PID", str(self.process.pid)], Path(sys.executable).parent)
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                self.process.kill()
        self.done.wait(10)


def background(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path, cap: int) -> Pump:
    """argv started in cwd, its stdout and stderr going to log through lib.logcap, which keeps the first cap
    bytes. The copier is its own process, so the cap holds after this one ends. OSError when PATH does not
    hold its program or it cannot start."""
    resolved = located(argv, env)
    if resolved is None:
        raise FileNotFoundError(not_on_path(argv[0]))
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_bytes(b"")
    group = {} if sys.platform == "win32" else {"start_new_session": True}
    copier = subprocess.Popen([sys.executable, str(LOGCAP), str(log), str(cap)], cwd=log.parent,
                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              **group)
    try:
        process = subprocess.Popen(list(resolved), cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL,
                                   stdout=copier.stdin, stderr=subprocess.STDOUT, **group)
    except OSError:
        copier.kill()
        raise
    finally:
        copier.stdin.close()
    return Pump(process, tuple(argv), log, copier)
