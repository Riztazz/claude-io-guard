"""Running a program from an argument list, with no shell and always with a timeout.

Task 25 adds background runs.
"""
import subprocess
import time
from collections.abc import Mapping, Sequence
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
