"""The checks on one command, and the profile of one file, offline, from the command line.

check builds the PreToolUse event a Bash or PowerShell call would send from a folder, and runs every check on
it with the live config of that folder's project, the way a hook would. It runs nothing and changes no file:
a body transport.body moves into a file, a warning's once-per-session key and the telemetry all stay in
memory. profile prints the line a Read gets.
"""
from dataclasses import replace
from pathlib import Path

from ioguard.checks.pipeline import Outcome, Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib import bytesio
from ioguard.lib.context import Context, LiveFs, SessionState, home_folder, project_root
from ioguard.lib.events import Event, Surface
from ioguard.lib.profile import profile
from ioguard.lib.telemetry import Telemetry

SESSION = "offline-check"


class DryFs(LiveFs):
    """The live file system, with every write kept in memory, so a check reads what it would have written."""

    def __init__(self) -> None:
        self.written: dict[Path, bytes] = {}

    def read_bytes(self, path: Path, limit: int | None = None) -> bytes:
        if path in self.written:
            return self.written[path] if limit is None else self.written[path][:limit]
        return super().read_bytes(path, limit)

    def write_atomic(self, path: Path, data: bytes) -> bytesio.WriteReport:
        self.written[path] = data
        return bytesio.WriteReport(path=path, bytes_written=len(data), attempts=0)

    def append(self, path: Path, data: bytes) -> None:
        self.written[path] = (self.read_bytes(path) if self.exists(path) else b"") + data

    def exists(self, path: Path) -> bool:
        return path in self.written or super().exists(path)

    def make_folders(self, path: Path) -> None:
        return None


def context(cwd: Path, env) -> Context:
    """The live context of cwd's project, with the file system, the session and the telemetry in memory."""
    registry = default_registry()
    live = Context.live(home_folder(env), project_root(cwd), registry.keys())
    return replace(live, fs=DryFs(), session=SessionState(), telemetry=Telemetry(None, enabled=False))


def check(command: str, cwd: Path, env, tool: str = "Bash") -> Outcome:
    """What every check decides about one command, sent to tool from cwd."""
    raw = {"hook_event_name": "PreToolUse", "session_id": SESSION, "tool_use_id": f"{SESSION}-1",
           "tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd),
           "permission_mode": "default", "transcript_path": ""}
    return Pipeline(default_registry()).run(Event.from_hook_json(raw, Surface.CLI), context(cwd, env))


def render(outcome: Outcome) -> str:
    """The verdict, each check that said something with its lines, and the command as it would run."""
    told = [f"Verdict: {outcome.verdict.name.lower()}"]
    for decision in outcome.decisions:
        lines = [*(result.render() for result in decision.results), *decision.context]
        if decision.rewrite is not None:
            lines.append(f"{decision.rewrite.code.value}: {decision.rewrite.note}")
        if lines:
            told.append(f"{decision.check_id}: {decision.verdict.name.lower()}")
            told += [f"  {line}" for line in lines]
    command = outcome.tool_input.get("command")
    if outcome.rewrites and isinstance(command, str):
        told += ["It would run as:", command]
    return "\n".join(told)


def profiled(path: Path) -> str:
    """The profile line a Read of path gets."""
    return f"{path.as_posix()}: {profile(bytesio.read_bytes(path)).line()}"
