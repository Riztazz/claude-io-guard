"""Running a program from an argument list, with no shell: to the end with a timeout, or in the background
with its output going to a log.

A background program starts in its own process group, so stopping it stops what it started too: taskkill /T
on Windows, and a signal to the group on macOS. Its stdin is empty, because nothing would ever answer a
prompt, and its stdout and stderr go to one log in the order the program flushes them.
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


def run(argv: Sequence[str], cwd: Path, env: Mapping[str, str] | None = None,
        timeout_s: float = 10.0) -> RunResult:
    """Run argv in cwd and wait. A timeout, or a program that cannot start, is a result, not a raise."""
    started = time.monotonic()
    command = tuple(argv)
    try:
        done = subprocess.run(command, cwd=cwd, env=None if env is None else dict(env), capture_output=True,
                              timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired as expired:
        return RunResult(command, None, expired.stdout or b"", expired.stderr or b"", True,
                         time.monotonic() - started)
    except OSError as error:
        return RunResult(command, None, b"", b"", False, time.monotonic() - started, start_error=str(error))
    return RunResult(command, done.returncode, done.stdout, done.stderr, False, time.monotonic() - started)


class Pump:
    """A program running with its output going to a log, and the moment it ended. A thread waits on the
    process, so ended is set even when nobody asks."""

    def __init__(self, process: subprocess.Popen, argv: tuple[str, ...], log: Path) -> None:
        self.process, self.argv, self.log = process, argv, log
        self.started = time.monotonic()
        self.ended: float | None = None
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.callbacks: list[Callable[[], None]] = []
        threading.Thread(target=self.watch, name="io-guard run", daemon=True).start()

    def watch(self) -> None:
        self.process.wait()
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
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.process.pid)], capture_output=True,
                           timeout=10, check=False)
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                self.process.kill()
        self.done.wait(10)


def background(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path) -> Pump:
    """argv started in cwd, its stdout and stderr going to log. OSError when it cannot start."""
    log.parent.mkdir(parents=True, exist_ok=True)
    group = {} if sys.platform == "win32" else {"start_new_session": True}
    with open(log, "wb") as out:
        process = subprocess.Popen(list(argv), cwd=cwd, env=dict(env), stdin=subprocess.DEVNULL, stdout=out,
                                   stderr=subprocess.STDOUT, **group)
    return Pump(process, tuple(argv), log)
