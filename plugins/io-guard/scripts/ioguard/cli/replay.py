"""Replay the corpus through the check pipeline, offline, and report what each check would have done.

Each record runs as a PreToolUse event, then as a PostToolUse or PostToolUseFailure event carrying its
recorded result. A shell call recorded without a structured response carries its result text as stdout.
Every session gets its own in-memory context: a file system that holds only the output Claude Code saved for
the call, read from disk while the file is still there, a clock that stands still, telemetry turned off, and
a git that answers from each repository's files as git tracks them now. Nothing runs but one git ls-files per
repository, nothing is written, and no check is skipped for time. A refusal of a call that succeeded is a
false-positive candidate, and the report keeps a sample of them. docs/design/architecture.md, section 11,
fixes the report's shape, which task 31 reads.
"""
import random
import re
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.cli.corpus import Record
from ioguard.cli.labels import SHELLS
from ioguard.lib import bytesio, output
from ioguard.lib.config import all_keys, defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, EventError, Surface
from ioguard.lib.git import Git, GitError, GitStatus
from ioguard.lib.platform import Platform, detect
from ioguard.lib.probing import Probe
from ioguard.lib.probing import WINDOWS_CUT, cut_applies
from ioguard.lib.results import render_many
from ioguard.lib.session import SessionState
from ioguard.lib.telemetry import Telemetry

REPORT_SCHEMA = 1
SAMPLE = 20
DRIVE = re.compile(r"^[A-Za-z]:")
WINDOWS = Platform("win32", True)
REPLAY_DATA = Path("replay-data")      # a data folder that exists only in the in-memory file system


class SnapshotGit:
    """A git port for replay that answers from each repository's tracked files as they are now. It runs one
    read-only git ls-files per repository and nothing else, and finds a repository by its .git entry."""

    def __init__(self) -> None:
        self.roots: dict[Path, Path | None] = {}
        self.files: dict[Path, frozenset[str]] = {}

    def within(self, seconds: float) -> SnapshotGit:
        return self

    @staticmethod
    def key(path: Path) -> str:
        return path.as_posix().lower()

    def root(self, path: Path) -> Path | None:
        for folder in (path, *path.parents):
            if folder in self.roots:
                return self.roots[folder]
            if (folder / ".git").exists():
                self.roots[folder] = folder
                return folder
        self.roots[path] = None
        return None

    def is_tracked(self, path: Path) -> bool:
        root = self.root(path)
        if root is None:
            return False
        if root not in self.files:
            try:
                self.files[root] = frozenset(self.key(file) for file in Git().ls_files(root))
            except GitError:
                self.files[root] = frozenset()
        return self.key(path) in self.files[root]

    def status(self, root: Path) -> GitStatus:
        return GitStatus(())

    def ls_files(self, root: Path) -> tuple[Path, ...]:
        return ()

    def changed_ranges(self, path: Path) -> None:
        return None

    def attributes(self, path: Path) -> dict:
        return {}


class Kind(Enum):
    """What a check's decision did to a recorded call. The report keys its counts by the value."""
    FIX = "fix"
    REFUSE = "refuse"
    WARN = "warn"


def kind_of(decision: Decision) -> Kind | None:
    """What a decision did to the call: refuse, fix, warn, or nothing."""
    if decision.verdict is Verdict.DENY:
        return Kind.REFUSE
    if decision.rewrite is not None:
        return Kind.FIX
    if decision.verdict is not Verdict.OBSERVE or decision.results or decision.context:
        return Kind.WARN
    return None


@dataclass
class CheckTally:
    counts: dict[Kind, Counter] = field(default_factory=lambda: {kind: Counter() for kind in Kind})
    events: Counter = field(default_factory=Counter)
    labels: Counter = field(default_factory=Counter)
    raised: int = 0
    samples: list[dict] = field(default_factory=list)
    candidates: int = 0

    def to_json(self) -> dict:
        return {**{kind.value: dict(self.counts[kind]) for kind in Kind}, "events": dict(self.events),
                "raised": self.raised, "labels": dict(self.labels.most_common()),
                "false_positive_candidates": self.candidates, "samples": self.samples}


class Replay:
    """One replay over a stream of records."""

    def __init__(self, registry: Registry, seed: int = 0, git: object | None = None) -> None:
        self.registry = registry
        self.git = git or SnapshotGit()
        self.pipeline = Pipeline(registry)
        self.config = defaults(registry.keys())
        self.keys = all_keys(registry.keys())
        self.sessions: dict[str, SessionState] = {}
        self.checks: dict[str, CheckTally] = defaultdict(CheckTally)
        self.tools: dict[str, Counter] = defaultdict(Counter)
        self.labels: Counter = Counter()
        self.unreadable = 0
        self.random = random.Random(seed)

    def context(self, record: Record) -> Context:
        """The context the recorded session would have had, with the probe's transport facts for its
        platform and Claude Code version, and every port in memory."""
        platform = WINDOWS if DRIVE.match(record.cwd) else detect()
        cut = cut_applies(platform.windows, record.version)
        probe = replace(Probe.unprobed(platform), transport_budget=WINDOWS_CUT if cut else None,
                        halving=True if cut else None)
        session = self.sessions.setdefault(record.session, SessionState())
        return Context.fake(saved_output(record), config=self.config, platform=platform, probe=probe,
                            session=session, git=self.git, telemetry=Telemetry(None, enabled=False),
                            data_dir=REPLAY_DATA, keys=self.keys)

    def events(self, record: Record) -> Iterable[Event]:
        raw = {"session_id": record.session, "cwd": record.cwd, "tool_name": record.tool,
               "tool_input": record.input, "tool_use_id": record.id,
               "permission_mode": record.permission_mode}
        yield Event.from_hook_json({**raw, "hook_event_name": "PreToolUse"}, Surface.CLI)
        if record.failed:
            failure = {**raw, "hook_event_name": "PostToolUseFailure", "error": record.result}
            yield Event.from_hook_json(failure, Surface.CLI)
        else:
            yield Event.from_hook_json({**raw, "hook_event_name": "PostToolUse",
                                        "tool_response": response_of(record)}, Surface.CLI)

    def run(self, record: Record) -> None:
        outcome_key = "failed" if record.failed else "ok"
        self.tools[record.tool][outcome_key] += 1
        self.labels.update(record.labels)
        ctx = self.context(record)
        try:
            events = list(self.events(record))
        except EventError:
            self.unreadable += 1
            return
        for event in events:
            outcome = self.pipeline.run(event, ctx)
            for check_id in outcome.errors:
                self.checks[check_id].raised += 1
            for decision in outcome.decisions:
                kind = kind_of(decision)
                if kind is None:
                    continue
                tally = self.checks[decision.check_id]
                tally.counts[kind][outcome_key] += 1
                tally.events[event.kind.value] += 1
                tally.labels.update(record.labels)
                if kind is Kind.REFUSE and not record.failed:
                    self.keep_sample(tally, record, decision)

    def keep_sample(self, tally: CheckTally, record: Record, decision: Decision) -> None:
        """Keep a uniform sample of the check's false-positive candidates, the same for the same corpus."""
        tally.candidates += 1
        sample = {"id": record.id, "project": record.project, "tool": record.tool,
                  "input": head(record), "reason": render_many(decision.results)}
        if len(tally.samples) < SAMPLE:
            tally.samples.append(sample)
            return
        slot = self.random.randrange(tally.candidates)
        if slot < SAMPLE:
            tally.samples[slot] = sample

    def report(self, seconds: float, corpus: Path, projects: Iterable[str]) -> dict:
        return {
            "schema": REPORT_SCHEMA,
            "corpus": str(corpus),
            "projects": sorted(projects),
            "checks_run": list(self.registry.ids()),
            "records": sum(sum(counts.values()) for counts in self.tools.values()),
            "unreadable": self.unreadable,
            "seconds": round(seconds, 1),
            "by_tool": {tool: dict(counts) for tool, counts in sorted(self.tools.items())},
            "by_label": dict(self.labels.most_common()),
            "checks": {check_id: tally.to_json() for check_id, tally in sorted(self.checks.items())},
        }


def response_of(record: Record) -> dict:
    """The recorded tool response, or a shell call's result text as its stdout when none was recorded."""
    if isinstance(record.response, dict):
        return record.response
    return {"stdout": record.result} if record.tool in SHELLS else {}


def saved_output(record: Record) -> dict[Path, bytes]:
    """The file Claude Code saved a shell call's long output to, while it is still on disk, by its path."""
    path = output.saved_path(response_of(record)) if record.tool in SHELLS and not record.failed else None
    if path is None or not Path(path).is_file():
        return {}
    return {Path(path): bytesio.read_bytes(Path(path))}


def head(record: Record) -> str:
    """The part of a call's input a reviewer reads first: the command, or the file path."""
    shown = record.input.get("command") or record.input.get("file_path") or record.input.get("pattern") or ""
    return str(shown)[:300]


def replay(records: Iterable[Record], registry: Registry, corpus: Path) -> dict:
    """Run every record through the pipeline, and return the report."""
    started = time.monotonic()
    run = Replay(registry)
    projects = set()
    for record in records:
        projects.add(record.project)
        run.run(record)
    return run.report(time.monotonic() - started, corpus, projects)


def render(report: dict) -> str:
    """The report as text a person reads: the corpus, then a line per check, then each check's samples."""
    tools = ", ".join(f"{tool} {counts.get('ok', 0)} ok and {counts.get('failed', 0)} failed"
                      for tool, counts in report["by_tool"].items())
    lines = [f"{report['records']} records from {', '.join(report['projects']) or 'no project'}, "
             f"replayed in {report['seconds']} s: {tools or 'none'}.",
             f"Checks run: {', '.join(report['checks_run']) or 'none, so every count below is zero'}."]
    labels = ", ".join(f"{name} {count}" for name, count in list(report["by_label"].items())[:12])
    lines.append(f"Top labels: {labels or 'none'}.")
    for check_id, tally in report["checks"].items():
        counts = "  ".join(f"{kind} {tally[kind].get('ok', 0)}/{tally[kind].get('failed', 0)}"
                           for kind in (each.value for each in Kind))
        lines.append(f"{check_id}: {counts}  raised {tally['raised']}  (ok/failed calls)")
        for sample in tally["samples"]:
            lines.append(f"  refused a call that ran: {sample['tool']} {sample['input']!r}")
    return "\n".join(lines)
