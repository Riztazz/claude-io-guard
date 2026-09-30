"""The session probe: at SessionStart, measure the machine once, save probe.json, and give shell calls UTF-8.

It runs in the SessionStart command hook, because CLAUDE_ENV_FILE belongs to a hook process. The tools'
versions are measured in parallel, and a version whose file has not changed since the last probe is kept. The
env file gets one export line per default, so every later Bash call starts with them. Only the user sets the
defaults, never a project, because a variable such as PYTHONSTARTUP or BASH_ENV runs a program (D24).

probe.json holds what is true of the machine, and every session on it shares the file. The files a session's
repository had changed when the session first started are the session's own, so they go to
sessions/<session>.dirty, written once. SessionStart fires again on a resume and a compaction, with the same
session id, and the list taken then would hold the session's own earlier work.
"""
import json
import logging
import re
import shlex
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import probing, proc
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent
from ioguard.lib.folders import session_file
from ioguard.lib.git import GitError
from ioguard.lib.platform import EVERY_PLATFORM
from ioguard.lib.ports import FsPort, GitPort
from ioguard.lib.probing import Probe, ToolVersion
from ioguard.lib.results import Layer, Severity

log = logging.getLogger("ioguard.checks.session_probe")

VERSIONS = {
    "bash": re.compile(r"version (\d+\.\d+\.\d+)"),
    "pwsh": re.compile(r"PowerShell (\d+\.\d+\.\d+)"),
    "git": re.compile(r"git version (\S+)"),
}
NOT_BASH = ("system32", "windowsapps")      # WSL's bash.exe and its store alias are not the Bash tool's shell
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ENV = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
ENV_WINDOWS = {"DOTNET_CLI_UI_LANGUAGE": "en", "VSLANG": "1033"}


def dirty_files(git: GitPort, cwd: Path) -> tuple[Path, ...] | None:
    """The changed and untracked files of cwd's repository, () outside one, None when git cannot say."""
    try:
        root = git.root(cwd)
        return () if root is None else tuple(root / entry.path for entry in git.status(root).entries)
    except GitError as error:
        log.info("The probe could not list the dirty files: %s", error)
        return None


def measure(event: Event, ctx: Context, dirty_wanted: bool) -> tuple[Probe, tuple[Path, ...] | None]:
    """The machine's facts, and the dirty files of the session's repository when dirty_wanted, else None."""
    env, previous = ctx.env, ctx.probe
    paths = {"bash": proc.on_path("bash", env, NOT_BASH if ctx.platform.windows else ()),
             "pwsh": proc.on_path("pwsh", env), "git": proc.on_path("git", env)}
    if ctx.platform.windows and env.get("CLAUDE_CODE_GIT_BASH_PATH"):
        paths["bash"] = env["CLAUDE_CODE_GIT_BASH_PATH"]
    with ThreadPoolExecutor(max_workers=min(4, ctx.config.get("io.server.workers"))) as pool:
        versions = {name: pool.submit(probing.tool_version, path, VERSIONS[name], getattr(previous, name))
                    for name, path in paths.items() if path}
        dirty = pool.submit(dirty_files, ctx.git, event.cwd) if dirty_wanted else None
    version = probing.claude_version(env)
    cut = probing.cut_applies(ctx.platform.windows, version)
    folder = ctx.data_dir or event.cwd
    probe = Probe(
        os=ctx.platform.os,
        bash=versions["bash"].result() if "bash" in versions else None,
        pwsh=versions["pwsh"].result() if "pwsh" in versions else None,
        python=ToolVersion.this_python(),
        git=versions["git"].result() if "git" in versions else None,
        console_encoding=probing.console_encoding(),
        fs_case_insensitive=probing.case_insensitive(folder, ctx.platform.case_insensitive),
        transport_budget=probing.WINDOWS_CUT if cut else None,
        halving=True if cut else None,
        claude_code_version=version,
        taken_at=ctx.clock.now(),
    )
    return probe, None if dirty is None else dirty.result()


def export_lines(values: Mapping[str, object]) -> tuple[list[bytes], list[str]]:
    """One export line per variable, and the names skipped because a shell cannot export them."""
    lines, skipped = [], []
    for name, value in values.items():
        if NAME.match(name) and isinstance(value, str):
            lines.append(f"export {name}={shlex.quote(value)}\n".encode("utf-8"))
        else:
            skipped.append(name)
    return lines, skipped


def add_lines(path: Path, lines: list[bytes], fs: FsPort) -> None:
    """Append the lines path lacks, keeping what another hook wrote there, before or during the append."""
    existing = fs.read_bytes(path) if fs.exists(path) else b""
    have = set(existing.splitlines(keepends=True))
    missing = [line for line in lines if line not in have]
    if missing:
        separator = b"" if not existing or existing.endswith(b"\n") else b"\n"
        fs.make_folders(path.parent)
        fs.append(path, separator + b"".join(missing))


class SessionProbe(Check):
    meta = CheckMeta(
        id="session.probe", layer=Layer.INTERNAL, events=frozenset({HookEvent.SESSION_START}),
        tools=frozenset(), platforms=EVERY_PLATFORM, severity=Severity.INFO,
        cost=Cost.EXPENSIVE, reads=frozenset(), writes=frozenset(), after=frozenset(), codes=frozenset(),
        config={
            "env": ConfigKey(dict, ENV, "Variables every later Bash call starts with.",
                             project_may_set=False, runs=True),
            "env_windows": ConfigKey(dict, ENV_WINDOWS, "More variables for Bash calls on Windows.",
                                     project_may_set=False, runs=True),
        },
        description="Measures the machine at session start and gives every shell call UTF-8 defaults.")

    def run(self, event: Event, ctx: Context) -> Decision:
        kept = None if ctx.data_dir is None else session_file(ctx.data_dir, event.session_id, "dirty")
        probe, dirty = measure(event, ctx, kept is not None and not ctx.fs.exists(kept))
        if ctx.data_dir is not None:
            data = (json.dumps(probe.to_json(), indent=1, ensure_ascii=True) + "\n").encode("ascii")
            ctx.fs.make_folders(ctx.data_dir)
            ctx.fs.write_atomic(ctx.data_dir / "probe.json", data)
        if kept is not None and dirty is not None:
            ctx.fs.make_folders(kept.parent)
            ctx.fs.write_atomic(kept, json.dumps([str(path) for path in dirty]).encode("ascii"))
        target = ctx.env.get("CLAUDE_ENV_FILE")
        if not target:
            return Decision.observe(self.meta.id)
        values = {**self.options["env"], **(self.options["env_windows"] if ctx.platform.windows else {})}
        lines, skipped = export_lines(values)
        add_lines(Path(target), lines, ctx.fs)
        if not skipped:
            return Decision.observe(self.meta.id)
        message = (f"io-guard left {', '.join(sorted(skipped))} out of the shell defaults, because a shell "
                   f"cannot export it. Give each checks.session.probe.env entry a name and a string value.")
        return Decision(self.meta.id, Verdict.ALLOW, user_message=message)
