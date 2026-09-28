# io-guard architecture

The design a new agent builds from. Written on 2026-09-27 for the plan in `.claude/tasks/`, after the review in
`review.md`, with the lead's decisions D12 to D21 from `.claude/tasks/context.md` folded in. Standard library
Python 3.14 or later, one codebase for Windows and macOS. `lib` is mechanism and holds nothing. `checks`, the
config and the tool contracts are policy. Every signature below is a contract, and a task that changes one updates
this page in the same change. The signatures write `Optional[X]` for readability, and the code writes `X | None`.
Python 3.14 defers annotations, so no module needs `from __future__ import annotations`.

## 1. Lay out the package

```
plugins/io-guard/
  .claude-plugin/plugin.json       name, userConfig (python), no bin/
  .mcp.json                        one stdio server, io, started from ${user_config.python}
  hooks/hooks.json                 mcp_tool hooks for tool events, one command hook for SessionStart
  skills/io-guard/SKILL.md         generated code and tool tables, hand-written steps
  ui/dashboard.html                the ui:// resource and the standalone page, one template
  scripts/
    hook.sh                        POSIX launcher for command hooks, Git Bash on Windows, sh on macOS
    hook.py                        command-hook entry point
    server.py                      MCP server entry point
    precommit.py                   the optional git pre-commit hook, which runs the cli's precommit command
    ioguard/
      __init__.py                  PLUGIN_VERSION, CONFIG_SCHEMA, CHECK_API, TELEMETRY_SCHEMA
      lib/                         mechanism, functions and frozen dataclasses only
        bytesio.py                 read_bytes, write_atomic, size guard
        profile.py                 Profile, profile, target_profile, convert_eol, with_bom, with_final_newline
        editorconfig.py            parse, matches, properties: the .editorconfig properties for one file
        drift.py                   drift, edited, changed_lines, restored: what a write changed in a file's bytes
        commands.py                command_for, filled: the user's verify and format commands per extension
        anchors.py                 find, blind, closest, unique_anchor, edit_view: where an old_string is, or
                                   nearly is
        edits.py                   replaced, change, apply, appended, wrapped, carried: changes placed as the
                                   Edit tool reads a file, and made in the file's own text
        indent.py                  style, reindented, around, fitted: new text in the indent of the lines where
                                   it lands
        shell.py                   scan, commands, budget_length, moved, pipelines, exit_candidates, the hazards
                                   bash reads differently
        pwsh.py                    commands, blanked, file_calls
        python_source.py           compile_report: a Python body's syntax error or warning, without running it
        paths.py                   normalise, msys_prefix, reserved, link_target, inside, resolved, LockTable
        git.py                     Git, the GitPort implementation
        locks.py                   holders, file_lock
        proc.py                    run, Pump, background
        results.py                 CodeSpec, CODES, Code, Result, Fix, render, callable_name
        config.py                  Config, SCHEMA, load, validate, merge
        events.py                  HookEvent, Tool, PermissionMode, Surface, Event
        context.py                 Context, the ports, SessionState, Probe
        decisions.py               Verdict, Rewrite, Decision, compose
        telemetry.py               Telemetry, TraceContext
        platform.py                Platform, detect
        probing.py                 tool_version, find, claude_version, console_encoding, case_insensitive
        text.py                    visible, snippet, head, invisible_added
        transcript.py              refusals: the calls Claude Code refused before any hook, from the transcript
        output.py                  exit_code, saved_path, error_lines, mojibake, excerpt: what a shell result says
        heartbeat.py               Heartbeat, parse, skipped_since: the io server's beat, and Claude Code's skip
        rules.py                   settings_files, load, match_argv: Claude Code's Bash and PowerShell deny and
                                   ask rules, met by an argument list
        runs.py                    interpreter, argv_of, key: what an io.run call runs
        patterns.py                problem, nested: a project file's regex that could stall a line's match
        commit_message.py          subcommand, sources, problems: where a git commit's message comes from, and
                                   what in it a policy forbids
      checks/                      policy, one module per check
        base.py                    Check, CheckMeta, Cost
        registry.py                Registry, default_registry
        pipeline.py                Pipeline, Outcome, Budget
        session_probe.py           SessionStart
        location.py                write.location: RESERVED_NAME, READ_ONLY, LINKED_PATH, dirty files.
                                   write.locks: FILE_LOCKED after a failed write
        transport_body.py          BODY_MOVED_TO_FILE, TRANSPORT_BUDGET, BACKSLASH_TRANSPORT
        shell_writes.py            SHELL_WRITE, scratch script warning
        lint.py                    shell.lint: quoting, escapes, dialect, Python bodies, PIPE_HIDES_EXIT
        win_paths.py               win.paths: MSYS_PATH for slash arguments and cmd /c, RESERVED_NAME for nul
        conform_write.py           conform.write: EOL_CONVERTED, BOM_RESTORED, EOL_MISMATCH for a mixed file
        conform_edit.py            conform.edit: INDENT_MISMATCH, new_string in the indent around the match
        verify_write.py            verify.write: the file after an Edit or Write against its snapshot, repairs
        verify_command.py          verify.command: the user's verify command on the written file
        touched.py                 shell.touched: TOUCHED_BY_SHELL, the files a shell command changed or made
        read_profile.py            read.profile: the profile line after Read, and the profile in read_profiles
        diagnose.py                diagnose.failure after a failed call, diagnose.refused at the next hook
        command_results.py         shell.results: EXIT_BENIGN, ERRORS_IN_OUTPUT, OUTPUT_SAVED, MOJIBAKE,
                                   STALE_BINARY, PIPE_HIDES_EXIT after the run, and the learned budget
        heartbeat.py               server.heartbeat: SERVER_DOWN at the start of a turn
        run_rules.py               run.rules: RULE_DENIED and RULE_ASKED at the PreToolUse hook on io.run
        commit_policy.py           commit.policy: COMMIT_POLICY for a commit message the user's policy forbids
      hooks/
        entry.py                   run_event: an event in, the answer dict out, never raising
        answer.py                  Outcome -> hook JSON, per event and rewrite mode
        bridge.py                  hook.* tools: substituted fields -> run_event -> the tool's text
      mcp/
        server.py                  stdio loop, threads, shutdown
        protocol.py                framing, _meta, eras, JSON-RPC errors
        toolspec.py                ToolSpec, schema generation, tools/list
        handles.py                 Handle, HandleStore, HandleExpired, STORE
        elicit.py                  Elicitor, LegacyElicitor, ModernElicitor, when a client shows a form
        progress.py                CancelToken, ProgressReporter
        in_place.py                held, load, write: a file an io tool changes, held, loaded and written once
        tools_read.py              io.read
        tools_edit.py              io.edit, io.splice, io.append
        tools_run.py               io.run, io.status, io.read_log
        tools_format.py            io.format
        tools_history.py           io.snapshot, io.restore, io.compare, io.stage
        tools_dashboard.py         io.dashboard, io.config, the ui resource
        tools_hook.py              hook.pre_tool_use, hook.post_tool_use, hook.post_tool_use_failure, hook.ping
        skill.py                   the skill page's tool and code tables, which tools/skill.py writes
      cli/
        main.py                    corpus, replay, precommit, report and measure today, then probe, check,
                                   profile, codes, serve, doctor
        labels.py                  the baseline's labels for a recorded call's result and command shape
        corpus.py                  Record, build, load: transcripts -> corpus/<project>.jsonl
        replay.py                  Replay, replay, render: the corpus through the pipeline, offline
        precommit.py               staged_results, run: each staged file against HEAD, for the git hook
        report.py                  files, summarise, render: the week's telemetry by code, tool and time
        measure.py                 measure, render: task 31's classes per 1,000 calls before and after io-guard
tests/                             mirrors ioguard, plus fixtures/, support/, mcp/, replay/
tools/                             ioguard.py, corpus.py, replay.py, measure.py, report.py, probes/
```

Four rules hold the layout together. `lib` imports only the standard library and other `lib` modules. `checks`
imports `lib`. `hooks`, `mcp` and `cli` are the ways in, and each imports `lib` and `checks` and never another,
except that `mcp.tools_hook` calls `hooks.bridge`. `tools/` scripts import `ioguard.cli`, or `ioguard.mcp.skill`
for the skill page, and hold no logic.

## 2. Define the core types

All types are frozen dataclasses or enums in `lib`. A value that crosses a module boundary is one of these.

### Event

```python
class HookEvent(Enum):
    SESSION_START = "SessionStart"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"

class Tool(Enum):
    BASH = "Bash"
    POWERSHELL = "PowerShell"
    EDIT = "Edit"
    WRITE = "Write"
    READ = "Read"
    GREP = "Grep"
    GLOB = "Glob"
    OTHER = "other"

class PermissionMode(Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    AUTO = "auto"
    DONT_ASK = "dontAsk"
    BYPASS = "bypassPermissions"

class Surface(Enum):
    COMMAND_HOOK = "command_hook"
    MCP_HOOK = "mcp_hook"
    MCP_TOOL = "mcp_tool"
    CLI = "cli"

@dataclass(frozen=True)
class Event:
    kind: HookEvent
    tool: Tool
    tool_name: str
    tool_input: Mapping[str, Any]
    tool_response: Optional[Mapping[str, Any]]
    error: Optional[str]
    session_id: str
    tool_use_id: Optional[str]
    prompt_id: Optional[str]
    cwd: Path
    scratchpad: Optional[Path]
    transcript: Optional[Path]       # the session's transcript, from transcript_path
    permission_mode: PermissionMode
    agent_id: Optional[str]
    surface: Surface
    raw: Mapping[str, Any]
    platform: Platform

    command: Optional[str]          # Bash and PowerShell, from tool_input["command"]
    file_path: Optional[Path]       # Edit, Write, Read, normalised once
    old_string: Optional[str]
    new_string: Optional[str]
    replace_all: bool
    content: Optional[str]

    @classmethod
    def from_hook_json(cls, raw: Mapping[str, Any], surface: Surface,
                       platform: Optional[Platform] = None) -> "Event": ...
    @classmethod
    def from_fields(cls, fields: Mapping[str, str], platform: Optional[Platform] = None) -> "Event": ...
    def with_tool_input(self, tool_input: Mapping[str, Any]) -> "Event": ...
```

An event the harness sends that io-guard cannot read, such as an unknown `hook_event_name` or no `cwd`, raises
`EventError`, and the entry point fails open around it. `tool_input` is read-only, and `with_tool_input` gives
the pipeline a new event with the derived fields worked out again. `platform` defaults to `platform.detect()`,
and a test passes another to read an event as the other platform would.

`from_hook_json` reads the harness JSON. `from_fields` rebuilds an event from the map an `mcp_tool` hook passes.
Every value in that map arrives as a string, and an absent one as an empty string (task 03, item 12). The scalars
come flat. `tool_input` and `tool_response` come whole, as the compact JSON text the harness substitutes for
`${tool_input}` and `${tool_response}`, and `from_fields` decodes them. That keeps an empty `new_string`, a
`replace_all` of `true` and a missing field apart, which a flat map of strings cannot. Both constructors normalise
`file_path` through `paths.normalise`. `tool` is `OTHER` for an MCP tool name, and `tool_name` keeps the full name.

### Context

```python
class GitPort(Protocol):
    def root(self, path: Path) -> Optional[Path]: ...
    def is_tracked(self, path: Path) -> bool: ...
    def status(self, root: Path) -> GitStatus: ...
    def ls_files(self, root: Path) -> tuple[Path, ...]: ...
    def changed_ranges(self, path: Path) -> Optional[tuple[LineRange, ...]]: ...   # since HEAD, task 26.
                                                                   # None when git has no commit of the file
    def attributes(self, path: Path) -> Mapping[str, str]: ...
    def staged(self, root: Path) -> tuple[str, ...]: ...           # added, changed or renamed, from root
    def blob(self, root: Path, spec: str) -> Optional[bytes]: ...  # "HEAD:a.py", or ":a.py" for the staged one

class FsPort(Protocol):
    def read_bytes(self, path: Path, limit: Optional[int] = None) -> bytes: ...
    def read_tail(self, path: Path, limit: int) -> bytes: ...       # the last whole lines in limit bytes
    def read_from(self, path: Path, offset: int, limit: int) -> bytes: ...   # task 25, for io.read_log
    def write_atomic(self, path: Path, data: bytes) -> WriteReport: ...
    def stat(self, path: Path) -> Optional[FileStat]: ...
    def exists(self, path: Path) -> bool: ...
    def holders(self, path: Path) -> tuple[Process, ...]: ...     # OSError when the platform cannot answer
    def make_folders(self, path: Path) -> None: ...
    def list_dir(self, path: Path) -> tuple[Path, ...]: ...   # the files in a folder, sorted, () when none
    def link_target(self, path: Path) -> Optional[Path]: ...  # where a path through a link really is
    def find_named(self, root: Path, name: str, limit: int) -> tuple[Path, ...]: ...  # a bounded walk

class Clock(Protocol):
    def now(self) -> datetime: ...
    def monotonic(self) -> float: ...

@dataclass(frozen=True)
class Probe:
    os: str                          # "win32" or "darwin"
    bash: Optional[ToolVersion]      # path and version, None without Git Bash
    pwsh: Optional[ToolVersion]
    python: ToolVersion
    git: Optional[ToolVersion]
    console_encoding: Optional[str]
    fs_case_insensitive: bool
    transport_budget: Optional[int]  # bytes, None where no cut exists or none was measured
    halving: Optional[bool]          # the Bash tool halves backslashes, None when not probed
    claude_code_version: Optional[str]
    dirty_at_start: Optional[tuple[Path, ...]]   # None when git could not answer, () outside a repository
    taken_at: Optional[datetime]

    @classmethod
    def unprobed(cls, platform: Platform) -> "Probe": ...   # before the session probe: the platform and Python
    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "Probe": ...
    def to_json(self) -> dict: ...

@dataclass(frozen=True)
class Snapshot:
    path: Path
    profile: Optional[Profile]                   # None for a file that does not exist yet
    data: Optional[bytes]                        # the bytes too, up to verify.write's snapshot_bytes
    tool_input: Mapping[str, Any]                # the input the tool runs with, after io-guard's rewrites

@dataclass(frozen=True)
class ShellSnapshot:                             # task 21, before a Bash or PowerShell command
    root: Optional[Path]                         # the session's repository, None outside one
    status: Optional[frozenset[tuple[str, str]]] # (path from root, XY) from git status, None when git fails
    stats: Mapping[Path, Optional[FileStat]]     # each read file's size and time

class SessionState:
    read_profiles: MutableMapping[Path, Profile] # the bytes the agent last read, or wrote through verify.write
    snapshots: MutableMapping[str, Snapshot | ShellSnapshot]   # by tool_use_id, until PostToolUse, 16 at most
    warned: MutableSet[str]                      # one user warning per key per session
    budget_override: Optional[int]               # learned from an EOF failure
    tracked: MutableMapping[Path, bool]          # whether git tracks a path, asked once by shell.writes
    asked_runs: MutableSet[str]                  # io.run calls run.rules put to the user, by runs.key, task 25
    read_logs: MutableMapping[Path, tuple[int, int]]   # io.read_log's last line and byte per log, task 25
    last_failed_build: Optional[str]             # the words of the build that last failed, task 22
    lock: RLock                                  # guards every field
    data_dir: Optional[Path]                     # with session_id, where the warned keys are shared, task 23
    session_id: Optional[str]

    @classmethod
    def shared(cls, data_dir: Optional[Path], session_id: str) -> "SessionState": ...
    def first_time(self, key: str) -> bool: ...  # True once per key in all the session's processes
    def keep_snapshot(self, tool_use_id: str, snapshot: Snapshot) -> None: ...   # the oldest past 16 goes
    def take_snapshot(self, tool_use_id: str) -> Optional[Snapshot]: ...         # handed out once

@dataclass(frozen=True)
class Context:
    config: Config
    probe: Probe
    platform: Platform
    git: GitPort
    fs: FsPort
    clock: Clock
    session: SessionState
    telemetry: Telemetry
    config_report: Optional[LoadReport] = None   # what loading the config found, for the one user message
    env: Mapping[str, str] = {}                  # the environment, so no check reads os.environ
    data_dir: Optional[Path] = None              # the plugin data folder

    @classmethod
    def live(cls, data_dir: Optional[Path], project: Path,
             check_keys: Optional[Mapping[str, Mapping[str, ConfigKey]]] = None) -> "Context": ...
    @classmethod
    def fake(cls, files: Optional[Mapping[Path, bytes]] = None, **overrides: Any) -> "Context": ...

def repository_root(git: GitPort, path: Path) -> Optional[Path]: ...   # None outside one or when git fails
def session_file(data_dir: Path, session_id: str, kind: str) -> Path: ...  # sessions/<session>.<kind>
def first_in_file(path: Path, data_dir: Path, key: str) -> bool: ...   # add key under file_lock, True if new
```

`Context.live` builds the real ports and loads the probe and the config from `${CLAUDE_PLUGIN_DATA}`. `lib`
cannot import the registry, so the caller passes `check_keys`, the registry's `keys()`, for the config to
validate. A probe field nobody has measured is `None`, never a guess. `Context.fake` builds in-memory ports
for tests from `lib.fakes`: a file system that takes a mapping of path to bytes, a git that answers what it
was given, and a clock that moves only when told. A check receives a `Context` and reads it. No check writes
into it except `session`, and only through its typed fields. A check reads the environment from `ctx.env`,
never from `os.environ`, and the plugin data folder from `ctx.data_dir`.

The session probe (`checks/session_probe.py`, task 10) writes `probe.json` at SessionStart, in the command hook
because `CLAUDE_ENV_FILE` belongs to a hook process. It measures Git Bash, pwsh and git with `--version` in
parallel, and a `ToolVersion` carries a `stamp`, the file's size and mtime, so an unchanged tool keeps its
version without running again. The Claude Code version comes from the hook's `AI_AGENT`, then from
`CLAUDE_CODE_EXECPATH`. On Windows `transport_budget` is the Bash tool's cut, 7,807 bytes with each apostrophe
counted as four, and `halving` is true, until `FIXED_IN` names the release that fixes #92543. The policy margin
below the cut, `transport.budget_bytes`, is task 11's key. A well-formed command over 5 KB that bash still reads
as ending inside a quote sets the session's `budget_override` below its length (task 22), and a budget learned
that way applies on a platform whose probe found no cut. The halving takes half the backslashes of a run
that a double quote does not follow: 4 become 2 and 3 become 2, while a run before `"` arrives whole
(`context.md`, row 25). `shell.scan` flags a pair as a hazard only where that changes what bash reads, and
`transport_body` moves a quoted heredoc or `python -c` body byte-exact when the command is over the budget or the
body holds a hazard (D25). The probe then appends `export` lines for the shell
defaults to `CLAUDE_ENV_FILE`, which reaches Bash calls and not PowerShell ones (`context.md`, row 23). A
session's first probe took 143 ms on Windows, and one that keeps every version about 55 ms.

### Result and the codes

```python
class Severity(Enum):
    FIXED = "fixed"        # the call ran after a mechanical fix
    WARNING = "warning"    # the call ran, context added
    REFUSED = "refused"    # the call did not run
    INFO = "info"          # a fact, such as a profile line

class Layer(Enum):
    LOCATION = 1
    TRANSPORT = 2
    BYTES = 3
    STALE = 4
    READ = 5
    OUTPUT = 6
    INTERNAL = 7

@dataclass(frozen=True)
class CodeSpec:
    code: str
    layer: Layer
    severity: Severity
    summary: str       # one sentence, present tense
    fix: str           # one sentence naming the tool to use
    since: str         # plugin version that introduced it

CODES: tuple[CodeSpec, ...] = (
    CodeSpec("BODY_MOVED_TO_FILE", Layer.TRANSPORT, Severity.FIXED,
             "The command body was written to a file and the command runs that file.",
             "Nothing to do.", "0.1"),
    CodeSpec("TRANSPORT_BUDGET", Layer.TRANSPORT, Severity.REFUSED,
             "The command is longer than this shell can carry.",
             "Write the script with the Write tool and run the file.", "0.1"),
)
Code = Enum("Code", {spec.code: spec.code for spec in CODES})

@dataclass(frozen=True)
class Fix:
    tool: str                       # "Edit", "Write", "Bash", or a callable MCP name
    input: Mapping[str, Any]
    text: str                       # the second sentence of the message

@dataclass(frozen=True)
class Result:
    code: Code
    severity: Severity
    message: str
    tool: str
    file: Optional[Path]
    evidence: Mapping[str, Any]
    fix: Optional[Fix]
    auto_fixed: tuple[Code, ...]
    platform: str

    def to_json(self) -> dict: ...
    def render(self) -> str: ...     # "CODE: what happened. What to do.", the fix on its own line after quoted lines
```

`CODES` is the one declaration. The `Code` enum, the skill's code table, the telemetry vocabulary and the
meta test that demands one producing test per code all read it. `Result.of(code, message, tool, platform)`
builds a result with the severity its code declares.

**`CODES` holds the codes that something already produces.** The meta test fails on a code no test names, so
a code enters `CODES` in the task that builds its check, with that check's tests. Task 07 settled the full
list below, and a task that needs a code not on it adds it here in the same change.

| Layer | Codes | Task |
|---|---|---|
| Location | `LINKED_PATH`, `READ_ONLY`, `FILE_LOCKED`. `OUTSIDE_WRITE_ROOT` was dropped with the write-roots rule (D27) | 19, in `CODES` |
| Transport | `BODY_MOVED_TO_FILE`, `TRANSPORT_BUDGET`, `BACKSLASH_TRANSPORT`, the last a warning (D25) | 11, in `CODES` |
| Transport | `SHELL_WRITE`, a warning for a new script inside a repository (GIT-1) | 12, in `CODES` |
| Transport | `BACKTICK_IN_DOUBLE_QUOTES`, `TRAILING_BACKSLASH_QUOTE`, `DIALECT_MISMATCH`, `POWERSHELL_TRAP`, `PIPE_HIDES_EXIT`, `INLINE_SCRIPT_INVALID` | 13, in `CODES` |
| Transport | `MSYS_PATH`, `RESERVED_NAME` | 14, in `CODES` |
| Bytes | `EOL_CONVERTED`, `BOM_RESTORED`, `EOL_MISMATCH`, `INDENT_MISMATCH` | 17, in `CODES` |
| Bytes | `BOM_CHANGED`, `ENCODING_INVALID`, `NON_ASCII_ADDED`, `CONTROL_BYTES_ADDED`, `SIZE_COLLAPSED`, `UNINTENDED_CHANGE`, all warnings | 18, in `CODES` |
| Stale | `ANCHOR_NOT_FOUND`, `ANCHOR_AMBIGUOUS`, `STALE_VIEW`, all warnings on a call that already failed, and refusals when an io tool of task 24 answers with them | 20, in `CODES` |
| Stale | `NOT_READ`, not built: the tool's own "not read yet" error already names the Read to make | - |
| Stale | `TOUCHED_BY_SHELL`, a warning | 21, in `CODES` |
| Read | `PATH_NOT_FOUND`, `READ_TOO_LARGE`, `PATTERN_INVALID`, `SEARCH_TOO_BROAD`, all warnings | 20, in `CODES` |
| Output | `EXIT_BENIGN`, `OUTPUT_SAVED`, `ERRORS_IN_OUTPUT`, `MOJIBAKE`, `STALE_BINARY` | 22, in `CODES` |
| Internal | `GUARD_ERROR`, `REWRITE_CONFLICT`, `BUDGET_EXCEEDED` | 07, in `CODES` |
| Internal | `SERVER_DOWN`, `CANCELLED` | 23, in `CODES` |
| Internal | `HANDLE_EXPIRED`, with the first tool that makes a handle | 25, in `CODES` |
| Transport | `RULE_DENIED`, `RULE_ASKED`, from `run.rules` and `io.run` itself | 25, in `CODES` |
| Transport | `COMMIT_POLICY`, a git commit whose message holds what `commit_policy` forbids | 29, in `CODES` |
| Bytes | `FORMAT_FAILED`, when `io.format`'s command cannot start, fails or prints nothing | 26, in `CODES` |
| Bytes | `INVISIBLE_ADDED`, a warning when a write adds a character the Read tool shows as nothing | 39, in `CODES` |

### Decision and Rewrite

```python
class Verdict(Enum):
    OBSERVE = 0      # nothing to say
    ALLOW = 1        # say something, let it run
    ASK = 2          # show the input to the user
    DENY = 3         # refuse with the fix

@dataclass(frozen=True)
class Rewrite:
    check_id: str
    fields: frozenset[str]                        # tool_input keys it changes
    apply: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    note: str                                     # the additionalContext line
    code: Code
    exclusive: bool = False                       # refuses composition on its fields

@dataclass(frozen=True)
class Decision:
    check_id: str
    verdict: Verdict
    results: tuple[Result, ...]
    rewrite: Optional[Rewrite]
    context: tuple[str, ...]                      # lines for the model
    user_message: Optional[str]                   # rare, shown once per session key
    classifier_note: Optional[str]                # PostToolUse classifierContext
    output_replacement: Optional[Mapping[str, Any]]  # PostToolUse updatedToolOutput
    latency_ms: float = 0.0

    @staticmethod
    def observe(check_id: str) -> "Decision": ...
```

A rewrite is a function, and the pipeline calls it on the running input. A check never mutates
`event.tool_input`. `exclusive` marks a rewrite that must own its fields, such as a whole-content replacement.

### Profile

```python
class Eol(Enum): CRLF, LF, CR, MIXED, NONE
class Bom(Enum): NONE, UTF8, UTF16_LE, UTF16_BE
class IndentKind(Enum): TABS, SPACES, MIXED, NONE

@dataclass(frozen=True)
class EolCounts:
    crlf: int
    lf: int
    cr: int

    @property
    def dominant(self) -> Eol: ...   # the ending most lines use, for a mixed file

@dataclass(frozen=True)
class Encoding:
    utf8: bool
    first_invalid: Optional[int]     # byte offset
    guess: Optional[str]             # "cp1250" or "cp1252"

@dataclass(frozen=True)
class Indent:
    kind: IndentKind
    width: Optional[int]
    tab_lines: int
    space_lines: int

@dataclass(frozen=True)
class ByteCounts:
    nul: int
    c0: int
    replacement: int
    private_use: int
    non_ascii: int
    trailing_ws_lines: int

@dataclass(frozen=True)
class Profile:
    eol: Eol
    eol_counts: EolCounts
    bom: Bom
    encoding: Encoding
    final_newline: bool
    line_count: int
    size: int
    indent: Indent
    counts: ByteCounts
    binary: bool
    sha256: str

    def line(self) -> str: ...        # "CRLF, BOM, UTF-8, tabs, 1,284 lines"
    def warnings(self) -> tuple[str, ...]: ...
    codec: str                        # property: reads the bytes whole, a BOM as U+FEFF, task 24
    new_eol: Eol                      # property: the file's ending, the dominant one when mixed, else LF
```

`profile` reads the style from the CRLF and LF counts, as the baseline survey did. A lone CR is counted and
warned about, and makes the style `CR` only in a file with no other ending. A UTF-16 file is counted in its
UTF-8 form, so its own NUL bytes do not mark it binary. It profiles a megabyte in about 11 ms (task 15).
`target_profile(siblings, editorconfig, gitattributes)` returns the `Profile` a new file takes, from the
`.editorconfig` properties that apply to it first, then its `.gitattributes`, then the majority of its siblings.
The caller resolves all three for the file's path. Its `sha256` is empty and its counts are zero.

## 3. Model a check

### The base class

```python
class Cost(Enum):
    CHEAP = 5          # estimated milliseconds, no IO beyond the event
    MEDIUM = 50        # reads files
    EXPENSIVE = 500    # runs a subprocess

@dataclass(frozen=True)
class ConfigKey:                             # in lib.config, which validates it and cannot import checks
    type: type
    default: Any
    doc: str
    project_may_set: bool = True
    choices: tuple = ()                      # the values it takes, or () for any of its type
    project_forbids: tuple = ()              # values a project file may not set
    project_narrows: bool = False            # a project file may lower this number and never raise it
    shape: Optional[Callable[[Any], Optional[str]]] = None   # what is wrong inside a list or dict value

@dataclass(frozen=True)
class CheckMeta:
    id: str                                  # "transport.body", stable forever
    layer: Layer
    events: frozenset[HookEvent]
    tools: frozenset[Tool]                   # empty means every tool
    platforms: frozenset[str]                # {"win32", "darwin"} or a subset
    severity: Severity                       # the default when the check finds something
    cost: Cost
    reads: frozenset[str]                    # tool_input fields it reads
    writes: frozenset[str]                   # tool_input fields its rewrite changes
    after: frozenset[str]                    # check ids that must run first
    config: Mapping[str, ConfigKey]          # its own keys under checks.<id>
    codes: frozenset[Code]                   # every code it can produce
    description: str                         # one sentence for the skill

class Check(ABC):
    meta: ClassVar[CheckMeta]

    def __init__(self, options: Mapping[str, Any]) -> None:
        self.options = options               # validated against meta.config at load

    def applies(self, event: Event, ctx: Context) -> bool:
        return (event.kind in self.meta.events
                and (not self.meta.tools or event.tool in self.meta.tools)
                and ctx.probe.os in self.meta.platforms)

    @abstractmethod
    def run(self, event: Event, ctx: Context) -> Decision: ...
```

A check is one class with one `run`. It holds its options and nothing else. State it needs across calls lives
in `ctx.session` under its own typed field. A check raises on a bug and returns a `Decision` for everything
expected.

### Registration

```python
class Registry:
    def register(self, check_class: type[Check]) -> None: ...
    def instantiate(self, config: Config) -> tuple[Check, ...]: ...
    def select(self, event: Event, ctx: Context) -> tuple[Check, ...]: ...
    def ids(self) -> tuple[str, ...]: ...

CHECKS: tuple[type[Check], ...] = (SessionProbe, Location, LockHolders, ShellWrites, TransportBody, Lint,
                                   WinPaths, ConformWrite, ConformEdit, VerifyWrite, VerifyCommand, Touched,
                                   ReadProfile, DiagnoseFailure, DiagnoseRefused, CommandResults, Heartbeat,
                                   RunRules, CommitPolicy)

def default_registry() -> Registry:
    registry = Registry()
    for check_class in CHECKS:
        registry.register(check_class)
    return registry
```

`register` validates as each check joins: a unique id, at least one event and one platform, every code a
member of `Code`, every `after` id already registered, and every config key with a readable type and a default
of that type, none of them named `enabled`, which every check gets. A check that runs after another joins
`CHECKS` after it, so the order has no cycle by construction. `writes` is enforced when the check runs: a
rewrite whose fields are not all in `writes` is a bug, and the pipeline fails open around it. Each check joins
`CHECKS` in the task that builds it. A test registers one class into an empty registry to test a check alone.
No import-time discovery, no decorators, one list. `transport.body` runs after `shell.writes`, so a command
refused for its write never has a body moved into a file first. `shell.lint` runs after `transport.body`, so it
compiles a moved body from its file, as Python will read it. `win.paths` runs after `shell.lint`, so its
rewrite lands on a command nothing refused. `verify.write` runs after `conform.write` and `conform.edit`, so
its snapshot holds the input the tool runs with. `verify.command` runs after `verify.write`, so a command
reads the file after any repair.

### The pipeline

```python
@dataclass(frozen=True)
class Budget:
    soft_ms: int = 300      # skip EXPENSIVE checks past this, config pipeline.soft_ms
    hard_ms: int = 2000     # skip everything past this, config pipeline.hard_ms

@dataclass(frozen=True)
class Outcome:
    verdict: Verdict
    tool_input: Mapping[str, Any]            # after every rewrite
    rewrites: tuple[Rewrite, ...]
    decisions: tuple[Decision, ...]
    context: tuple[str, ...]
    user_message: Optional[str]
    classifier_note: Optional[str]
    output_replacement: Optional[Mapping[str, Any]]
    skipped: tuple[str, ...]                 # check ids skipped by the budget
    errors: tuple[str, ...]                  # check ids that raised

class Pipeline:
    def __init__(self, registry: Registry, budget: Budget) -> None: ...
    def run(self, event: Event, ctx: Context) -> Outcome: ...
    def order(self, checks: tuple[Check, ...]) -> tuple[Check, ...]: ...
```

`run` does these steps in order.

1. **Select.** `registry.select` keeps the checks whose `applies` is true and whose `enabled` option is true.
2. **Order.** Sort by `(layer, cost, id)`, then move each check after every id in its `after` set. The layer
   order puts refusals about location first, then the transport rewrites, then the byte rewrites. A cycle in
   `after` fails at registration.
3. **Run and chain.** Each check receives an event whose `tool_input` is the running input. When a decision
   carries a rewrite, `compose` applies it and the running input changes for the checks that follow. The
   budget check in `transport_body` therefore measures the moved-body command, not the original.
4. **Resolve conflicts.** Two rewrites on disjoint fields compose. Two on a shared field compose in order
   unless either is `exclusive`, in which case the later one is dropped and a `REWRITE_CONFLICT` warning names
   both checks. Every dropped rewrite is telemetry.
5. **Stop on a refusal.** The first `DENY` ends the run. Its result renders as the reason, and the results of
   the checks that ran before it render as extra lines.
6. **Hold the budget.** Before each check, the pipeline compares elapsed time with the budget. Past `soft_ms`
   it skips `EXPENSIVE` checks. Past `hard_ms` it skips everything left. Each skip is `BUDGET_EXCEEDED` in
   telemetry, and the call proceeds with what was decided.
7. **Fail open.** A check that raises is skipped, logged as `GUARD_ERROR` with the traceback in the debug log,
   and named once per session in a `user_message`. The run continues with the next check.
8. **Merge.** The verdict is the maximum of the decisions. Context lines join in order: each decision's
   results rendered, except a refusal's, which are its reason, then its context lines, then the pipeline's own
   warnings. One `output_replacement` at most, from the first check that offers one.

Idempotence is a tested property, not a convention. `pipeline.run` on the input of a previous `Outcome` must
produce no rewrite and the same verdict. Every rewrite therefore recognises its own output: a moved body leaves
no heredoc, and CRLF content converts to CRLF unchanged.

## 4. Name the lib functions

Each module lists its public functions. Every one takes values and returns values.

```python
# bytesio.py
def read_bytes(path: Path, limit: Optional[int] = None) -> bytes
def read_tail(path: Path, limit: int) -> bytes               # task 20: from the first line break it holds
def write_atomic(path: Path, data: bytes, retries: int = 5) -> WriteReport

# drift.py, task 18
def drift(before: Profile, after: Profile) -> Drift         # endings, BOM, encoding and odd bytes that changed
def edited(before: str, old: str, new: str, replace_all: bool) -> Optional[Edited]   # the text and new lines
def changed_lines(expected: str, actual: str) -> tuple[int, ...]   # endings read as LF, BOM dropped
def lines_holding(text: str, pattern: Pattern, among: Optional[tuple[int, ...]] = None) -> tuple[int, ...]
def would_collapse(expected: int, actual: int, percent: int) -> bool
def restored(data: bytes, eol: Optional[Eol], bom: Bom) -> Optional[bytes]   # None when data is not UTF-8

# commands.py, task 18 as verify.py, and task 26
def verify_problem(value: Mapping[str, Any]) -> Optional[str]           # ConfigKey.shape of the verify key
def format_problem(value: Mapping[str, Any]) -> Optional[str]           # and of the format key
def command_for(value: Mapping[str, Any], path: Path, platform: Platform) -> Optional[tuple[str, ...]]
def filled(command: Sequence[str], path: Path, ranges: Sequence[tuple[int, int]] = ()) -> tuple[str, ...]
                                                            # {file}, and the {first}:{last} argument per range

# profile.py
def profile(data: bytes) -> Profile
def target_profile(siblings: Sequence[Profile], editorconfig: Mapping[str, str],
                   gitattributes: Mapping[str, str]) -> Profile
def convert_eol(text: str, eol: Eol) -> str                  # MIXED and NONE leave text as it is
def with_bom(text: str, bom: Bom) -> str                     # a leading U+FEFF, which Write writes as EF BB BF
def with_final_newline(text: str, final: bool, eol: Eol) -> str

# editorconfig.py, task 17
def parse(text: str) -> tuple[bool, list[tuple[str, dict[str, str]]]]   # root = true, then the sections
def matches(glob: str, relative: str) -> bool               # *, **, ?, [set], [!set], {a,b}
def properties(path: Path, read: Callable[[Path], Optional[str]]) -> dict[str, str]
                                                            # up the folders to root = true, nearer wins

# anchors.py, task 20: text as the Edit tool reads it, every ending as LF and no BOM
def find(text: str, anchor: str) -> tuple[Match, ...]       # each place, not overlapping, with its lines
def blind(text: str, anchor: str) -> tuple[Match, ...]      # each place with spaces and tabs ignored
def closest(text: str, anchor: str, limit: int = 3) -> tuple[Candidate, ...]  # blind, or scored windows
def unique_anchor(text: str, match: Match) -> str           # whole lines around match, below then above
def edit_view(text: str) -> str                             # task 24: every CRLF and lone CR as LF

# edits.py, task 24: a place in the LF view, the change in the file's own text
def replaced(text: str, start: int, end: int, new: str, eol: Eol) -> str   # each break in new as eol
def change(text: str, start: int, end: int, new: str, eol: Eol, width: Optional[int]) -> Changed
                                                            # and new in the indent around it
def apply(text: str, changes: Sequence[Change], eol: Eol, width: Optional[int]) -> Applied | Missed
                                                            # in order, each old found once, or none made
def appended(text: str, addition: str, eol: Eol) -> str     # a last line with no break keeps having none
def wrapped(text: str, column: int) -> str                  # a list item hangs under its first word
def lines_of(text: str) -> list[tuple[str, str]]            # task 26: each line and its CRLF, LF or no ending
def carried(text: str, other: str, eol: Eol, within: Optional[Sequence[tuple[int, int]]] = None) -> Carried
                                                            # task 26: other in text's endings, changes that
                                                            # meet no line of within left as text had them

# indent.py, task 24, moved from conform_edit
def style(text: str) -> str                                 # tabs, spaces, mixed or none
def reindented(text: str, to: str, width: int) -> str
def around(text: str, first: int, last: int) -> str         # three lines either side
def fitted(new: str, near: str, width: Optional[int]) -> Optional[str]   # None when the styles agree

# shell.py, task 11
def scan(command: str) -> Scan              # heredocs, python -c bodies, halving hazards, quoting states
def budget_length(command: str) -> int      # UTF-8 bytes, apostrophes count four
def moved(command: str, heredocs: Mapping[Heredoc, str], bodies: Mapping[InlineBody, str]) -> str
def shell_path(path: str) -> str            # a path as a double-quoted bash word
def exec_file(path: str) -> str             # the python -c argument that runs a file as -c ran its body
# shell.py, task 12
def commands(command: str, found: Optional[Scan] = None) -> tuple[SimpleCommand, ...]
                                            # split at ; & | ( ) and newlines outside quotes, bodies, comments
class SimpleCommand: words, redirects, inputs, span, name  # words unquoted, leading assignments dropped
class Redirect: target, append, fd                          # a file only: 2>&1 and >&2 are never one
# shell.py, task 13
Scan.backticks, Scan.unterminated           # unescaped backticks in double quotes, a quote left open at the end
def call_operators(command: str, states: bytes) -> tuple[int, ...]   # an & that starts a command
def trailing_backslash_paths(command: str) -> tuple[tuple[int, int], ...]   # "C:\dir\" escaping its quote
def forward_slashed(command: str, spans: Sequence[tuple[int, int]]) -> str
def piped(command: str, simple: SimpleCommand) -> bool      # its output goes into | or |&
def python_reads_stdin(simple: SimpleCommand) -> bool       # python or python -, with no script, -c or -m
def body_files(command: str) -> tuple[str, ...]             # the moved body files the command reads
# shell.py, task 22
def matching(simple: SimpleCommand, entries: Sequence[str]) -> Optional[str]   # the words of the entry it runs
def pipelines(command: str) -> Optional[tuple[Pipeline, ...]]   # with &&, || or ; before each, None when grouped
def exit_candidates(command: str) -> tuple[SimpleCommand, ...]  # those that can have set the exit code, last first

# pwsh.py, task 12
def commands(command: str) -> tuple[SimpleCommand, ...]     # split at ; | && || and newlines, here-strings whole
def file_calls(command: str) -> tuple[str, ...]             # the literal paths [IO.File] write calls name
# pwsh.py, task 13
def blanked(command: str) -> str                            # strings and comments as spaces, code left

# python_source.py, task 13
def compile_report(source: str) -> Optional[CompileReport]  # the SyntaxError, or the SyntaxWarnings

# paths.py
def normalise(raw: str, cwd: Path, platform: Platform) -> Path   # a Windows path with forward slashes
def shown(path: Path, cwd: Path) -> str                     # from cwd when under it, and cwd as words
def msys_prefix(word: str, posix_roots: Collection[str]) -> Optional[str]   # task 14: what Git Bash must keep
def reserved(path: Path) -> Optional[str]                   # "nul" for nul.txt, the name before the first dot
def link_target(path: Path) -> Optional[Path]               # through a junction or symlink, None through none
def inside(path: Path, roots: Collection[Path], platform: Platform) -> Optional[Path]   # the deepest root
def resolved(path: Path) -> str                             # task 24: links followed, case folded as named
class LockTable: lock(path) -> threading.Lock               # task 24: one per resolved path, per process

# git.py
class Git(GitPort): ...                                     # every call: -c core.quotepath=false, -z, timeout
def parse_status(raw: bytes) -> GitStatus
def parse_ranges(raw: bytes) -> tuple[LineRange, ...]
def parse_attributes(raw: bytes) -> dict[str, str]

# locks.py
def holders(path: Path, platform: Platform) -> tuple[Process, ...]   # task 19: Restart Manager or lsof
def parse_lsof(raw: bytes) -> tuple[Process, ...]
def file_lock(path: Path, data_dir: Path, wait_s: float = 5.0) -> ContextManager[None]  # across processes

# proc.py
def run(argv: Sequence[str], cwd: Path, env: Optional[Mapping[str, str]] = None,
        timeout_s: float = 10.0, stdin: bytes = b"") -> RunResult   # a timeout or a missing program is a
                                                            # result, and stdin is never the caller's own
def background(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path) -> Pump
                                                            # task 25: stdout and stderr in one log
class Pump: exit_code, wait(timeout_s), when_done(callback), seconds(), stop()   # stop ends the whole tree

# runs.py, task 25
def interpreter(lang: str, probe: Probe, platform: Platform) -> Optional[tuple[str, ...]]
def argv_of(given: Mapping[str, Any], probe: Probe, platform: Platform, body: Optional[str] = None)
    -> Optional[tuple[str, ...]]                            # argv, or the interpreter and the body's file
def key(given: Mapping[str, Any]) -> str                    # one per command, which run.rules records

# patterns.py, task 25
def problem(pattern: str) -> Optional[str]                  # does not compile, over 200 characters, or nested
def nested(pattern: str) -> bool                            # a quantified group whose text holds a quantifier

# results.py
def spec(code: Code) -> CodeSpec
def render(result: Result) -> str
def render_many(results: Sequence[Result]) -> str
def callable_name(name: str) -> str       # io.edit -> mcp__plugin_io-guard_io__io_edit, for every fix text

# config.py
def defaults(check_keys: Optional[Mapping[str, Mapping[str, ConfigKey]]] = None) -> Config
def load(layers: Sequence[ConfigLayer], check_keys: Mapping[str, Mapping[str, ConfigKey]]) -> LoadReport
def validate(raw: Any, scope: Scope, keys: Mapping[str, ConfigKey],
             file: Optional[Path] = None) -> tuple[ConfigError, ...]
def merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]   # on dotted keys

# decisions.py
def compose(rewrites: Sequence[Rewrite], tool_input: Mapping[str, Any]) -> ComposeResult
def conflict_with(rewrite: Rewrite, applied: Sequence[Rewrite]) -> Optional[Rewrite]
def apply_one(rewrite: Rewrite, tool_input: Mapping[str, Any]) -> dict   # RewriteError on an undeclared field

# telemetry.py
class Telemetry:
    def record(self, event: TelemetryEvent) -> None
    def flush(self) -> None
def trace_from(tool_use_id: Optional[str], traceparent: Optional[str]) -> TraceContext

# platform.py
def detect() -> Platform

# text.py, task 20
def visible(text: str) -> str                 # [TAB], [CR], [BOM], [SP] at a line's end, [U+E0A0]
def snippet(text: str, first: int, last: int, around: int = 2) -> str   # numbered as the Read tool does
def head(text: str, limit: int) -> str        # cut, with the count of what was cut
def invisible_added(before: str, after: str, allowed: frozenset[str] = frozenset()) -> tuple[tuple[int, str], ...]
                                              # task 39: each new Cf, no-break, separator or private-use
                                              # character, as U+XXXX, at its first line

# transcript.py, task 20
def refusals(tail: bytes) -> tuple[Refusal, ...]   # the refused calls after the last call that ran

# heartbeat.py, task 23
def parse(data: bytes) -> Optional[Heartbeat]      # pid, session, era, started, beat, stopped
def skipped_since(cache: bytes, server: str, default_ttl_s: float) -> Optional[tuple[datetime, datetime]]
                                                   # when Claude Code gave up on server, and when it tries again

# output.py, task 22
def exit_code(error: str) -> Optional[int]                     # from a failed call's first line, Exit code N
def saved_path(response: Mapping[str, Any]) -> Optional[str]   # persistedOutputPath, or the path its notice names
def error_lines(text: str, patterns: Mapping[str, Pattern]) -> tuple[ErrorLine, ...]   # matched from line start
def mojibake(text: str, code_pages: Sequence[str]) -> Mojibake # U+FFFD, and UTF-8 a console read in a code page
def excerpt(text: str, head: int, tail: int, marked: Sequence[ErrorLine], width: int) -> str   # numbered lines

# rules.py, task 25
def settings_files(env: Mapping[str, str], project: Path, platform: Platform) -> tuple[Path, ...]
                                                            # managed, user, project, project local
def load(files: Sequence[Path], read: Callable[[Path], Optional[bytes]]) -> Rules   # deny and ask rules
def match_argv(rules: Rules, argv: Sequence[str]) -> RuleMatch   # deny, then ask, then none
def command_text(words: Sequence[str]) -> str               # a word with a space or quote in single quotes
def unwrapped(words: Sequence[str]) -> list[str]            # timeout, nohup, NAME=value and the rest stripped
def named(words: Sequence[str]) -> list[str]                # the program by its bare name
```

## 5. Configure the policy

Policy data lives in `io-guard.json`. The file carries no comments, so its keys carry their meaning.

```json
{
  "schema": 1,
  "checks": {
    "transport.body": {"enabled": true},
    "win.paths": {"enabled": true, "prefixes": []},
    "verify.write": {"enabled": true, "ascii_only": [".md", ".py"]}
  },
  "transport": {
    "budget_bytes": 6000,
    "rewrite_mode": {"default": "ask", "acceptEdits": "ask", "plan": "ask",
                     "auto": "refuse", "dontAsk": "refuse", "bypassPermissions": "allow"}
  },
  "pipeline": {"soft_ms": 300, "hard_ms": 2000},
  "skip_trees": ["Content/**", "Binaries/**"],
  "verify": {".py": ["python", "-m", "py_compile", "{file}"], ".cpp": ["clang-format", "--dry-run", "{file}"]},
  "noise_patterns": ["^LogTemp: Display:"],
  "telemetry": {"enabled": true, "retention_days": 90, "debug": false},
  "commit_policy": {"forbid": ["Co-Authored-By", "Generated with"], "ascii_only": true}
}
```

Four layers merge in this order, and a later layer overrides an earlier one key by key.

| Layer | File | May widen |
|---|---|---|
| Defaults | `config.defaults()` in code | |
| User | `${CLAUDE_PLUGIN_DATA}/config.json` | yes |
| Project | `<project>/.claude/io-guard.json` | no |
| Project local | `<project>/.claude/io-guard.local.json`, gitignored | no |

**Every policy value is a key here, with its default in code (D16).** A number that decides behaviour and has no
key is a defect. The values above are the defaults the lead set on 2026-09-27. A key enters `lib.config` with
the code that reads it, because a key nothing reads is a validation error in waiting. Task 07 defined
`schema`, `pipeline.*`, `transport.rewrite_mode.*` and `telemetry.*`, task 10 `checks.session.probe.env` and
`env_windows`, task 11 `transport.budget_bytes`, and task 13 `checks.shell.lint.build_commands`, the commands
whose exit code a pipe hides, each as its first words, such as `make` or `npm test`. A project names its own
builds there, and its list replaces the default one. Task 14 added `checks.win.paths.posix_roots`,
`msys_programs` and `prefixes`. The check finds the slash arguments Git Bash would convert on its own, so
`prefixes` is only for a name that looks like a POSIX root. Task 16 added `checks.read.profile.max_bytes`, 16 MB,
the largest file that gets a profile line after a Read. Task 18 added `verify`, and
`checks.verify.write.repair`, `ascii_only`, `collapse_percent`, `snapshot_bytes` of 2 MB and `max_bytes` of
16 MB, and `checks.verify.command.timeout_ms` of 10 s and `output_chars` of 2,000. `verify` and `ascii_only`
default to empty, so io-guard runs no program and accepts non-ASCII until a user or a project names them. The
example above shows them set. Task 20 added `checks.diagnose.*.find_limit`, `part_bytes` and `tail_bytes`, and
task 21 `skip_trees`, empty by default, and `checks.shell.touched.listed`. Task 22 added
`checks.shell.results.error_patterns` and `benign_exits`, both merged key by key with a project's own,
`readers`, `builds`, `runs`, `short_lines` of 50, `head_lines` and `tail_lines` of 20, `shown_errors`,
`line_chars`, `max_bytes` of 16 MB, `code_pages` and `learn_from_bytes` of 5,000. Task 23 added
`io.read.max_bytes` of 16 MB and `io.read.max_chars` of 60,000, and `checks.server.heartbeat.stale_s` of 30.
Task 24 added `io.edit.max_bytes` of 16 MB and `io.edit.wait_ms` of 5,000, which `io.edit`, `io.splice` and
`io.append` share. Task 25 added `io.run.timeout_s` of 120, `io.run.handle_ttl_s` of 3,600,
`io.read_log.max_lines` of 500 and `noise_patterns`. Task 26 added `format`, the command `io.format` runs per
extension, clang-format for C and C++ by default, and `io.format.timeout_s` of 30. Task 29 added
`commit_policy.forbid`, empty and the user's alone, and `commit_policy.ascii_only`, false, which a project file
may only turn on. Task 39 added `invisible_allowed`, the characters, as `U+00A0`, a write may add without an
`INVISIBLE_ADDED` warning. A key marked `project_regex`, `noise_patterns` and `checks.shell.results.error_patterns`,
holds regexes io-guard runs on every line of output, and Python's `re` has no timeout. So a project file's
pattern that does not compile, is over 200 characters, or repeats a group that repeats inside, such as
`(a+)+`, drops the file (`lib.patterns`). The user's own `config.json` may still set one.
Each other key arrives with its check. A key marked `project_narrows`, such as
the budget, takes a lower number from a project file and refuses a higher one. A key with a `shape`, such as
`verify`, has its inner values checked too, and a wrong one drops the file like any other error.

**The rewrite mode is the user's (D12).** For each permission mode the user layer sets `refuse`, `ask` or `allow`.
In `refuse` the call is refused and the reason carries the corrected command, so the model reruns it and the
auto-mode classifier judges it. In `ask` the user sees the corrected command. In `allow` it runs at once and no
classifier sees it. `/plugin configure io-guard` cannot set nested keys, so the user edits `config.json`, calls
`io.config`, or uses the dashboard page, and the README shows each.

A project file restricts and never widens. It disables a check, adds `skip_trees` and `noise_patterns`, and
narrows `budget_bytes`. It cannot set `verify` or `format` commands, set `rewrite_mode` to `allow`, or turn telemetry
off. `ConfigKey.project_may_set` marks each check key. The scope rule exists because a cloned repository must
not be able to approve commands or make io-guard run a program (D24). A `verify` or `format` command is a
program io-guard starts, so only the user's own `config.json` names one. Each key maps an extension to a
command, such as `".py": ["python", "-m", "py_compile", "{file}"]`, and an absolute project root to its own map
of extensions, which wins for that project's files (task 18). A format command's argument that holds `{first}`
and `{last}` repeats once per line range (task 26).

Loading happens once per process and fails loudly. `validate` reports an unknown key with the file, the key
and the nearest known key, a type mismatch with the expected type, and a scope violation with the layer that
may set it. A file with errors is dropped whole, the guard runs with the layers that loaded, and one
`user_message` names the file and the first error. Dictionaries deep-merge, lists replace, and a list key that
ends in `extra` appends.

## 6. Run the hooks

### The command entry point

`scripts/hook.py <event>` reads stdin as bytes, decodes UTF-8, calls `hooks.entry.run_event`, writes one ASCII
JSON answer to stdout and exits 0. Nothing else reaches stdout. A crash before the answer is written prints `{}`
and logs `GUARD_ERROR` to stderr. The `ioguard` logger has a `NullHandler`, so a log record reaches only
`debug.log`, and only when `telemetry.debug` is true.

```python
def run_event(raw: Mapping[str, Any], surface: Surface, ctx: Optional[Context] = None,
              registry: Optional[Registry] = None) -> dict:
    """Runs the pipeline for one hook event and returns the harness answer. It never raises."""
```

`run_event` reads `raw` with `Event.from_fields` for `Surface.MCP_HOOK` and with `Event.from_hook_json` for the
others. Without `ctx`, it takes the live context for the event's session and working directory from
`hooks.entry.CONTEXTS`, which loads the config and the probe once per session and project and keeps one
`SessionState` per session. The data folder is `IOGUARD_DATA` in the server and `CLAUDE_PLUGIN_DATA` in a
command hook. Without `registry`, it runs `default_registry()`. An event it cannot read answers `{}`. A bug past
the pipeline's own fail-open answers `{}`, logs `GUARD_ERROR`, and warns the session once. The config's one
message, when a file was dropped, goes out with the session's first answer in that project.

`hooks.answer` turns an `Outcome` into the event's JSON. For PreToolUse the verdict and the rewrite mode decide
the shape, and a refusal outranks an ask, which outranks an allow.

| Outcome | Answer |
|---|---|
| OBSERVE or ALLOW, no rewrite | `{}`, or `additionalContext` only. No `permissionDecision`, so no prompt is skipped |
| DENY | `permissionDecision: "deny"`, the refusing check's results rendered first in the reason, then the lines of the checks before it |
| ASK, no rewrite | `permissionDecision: "ask"` with the check's lines as the reason |
| file-tool rewrite, no ASK or DENY | `updatedInput` and the notes in `additionalContext`, no `permissionDecision` |
| rewrite, mode `ask`, or any rewrite with an ASK | `permissionDecision: "ask"`, `updatedInput`, the notes in `permissionDecisionReason` |
| rewrite, mode `allow` | `permissionDecision: "allow"`, `updatedInput`, the notes in `additionalContext` |
| rewrite, mode `refuse` | `permissionDecision: "deny"`, the notes, then the command to run instead, or the changed fields as JSON |

A rewrite's note renders as `CODE: note`. The mode comes from `transport.rewrite_mode[permission_mode]`, and
applies to shell rewrites. A file-tool rewrite from `conform_write` and `conform_edit` answers with
`updatedInput`, the notes in `additionalContext`, and no `permissionDecision`. The harness then applies the
conformed input and asks or approves as it would have for the original call: task 17's `write-quiet` probe saw
the permission prompt show the rewritten content, BOM and CRLF, on 2.1.281 and 2.1.283 (`context.md`, "Hooks
and MCP", row 27). A check's own ASK or DENY still outranks it.

`verify.write` is the one check that writes after a tool has. It puts back a BOM or line endings the write
lost, through `write_atomic`, and its answer tells the agent to read the file again. An Edit straight after
such a repair succeeded without a new Read on 2.1.281 and 2.1.283 (`context.md`, "Hooks and MCP", row 29).

PostToolUse answers carry `additionalContext`, `classifierContext` and `updatedToolOutput`. An
`updatedToolOutput` has the tool's own output shape: for Bash and PowerShell, the `tool_response` object with
`stdout` replaced. A plain string there fails the harness's schema check and changes nothing. `shell.results`
replaces a saved output with its first and last lines and its error lines, and drops `persistedOutputPath` and
`persistedOutputSize` from it, because with them Claude Code shows the replacement only as the 2 KB preview of
the saved file (`context.md`, "Hooks and MCP", row 32). A failed Bash or PowerShell call brings no
`tool_response`, and its output follows the `Exit code N` line in `error`. PostToolUseFailure answers carry
`additionalContext`. SessionStart answers carry `additionalContext` and write `CLAUDE_ENV_FILE`. The
user's `systemMessage` is the outcome's `user_message` on every event. PreToolUse `additionalContext` reaches
the model with and without a permission decision, as a `hook_additional_context` attachment in the transcript
(`context.md`, "Hooks and MCP", row 22).

### The mcp_tool alternative

The plugin's `hooks.json` binds every tool event to a tool on the plugin's own server. The server is the
scoped name `plugin:io-guard:io`, and the tools are `hook.pre_tool_use`, `hook.post_tool_use` and
`hook.post_tool_use_failure`.

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|PowerShell|Edit|Write|Read|Grep|Glob|mcp__plugin_io-guard_io__io_run",
      "hooks": [{
        "type": "mcp_tool",
        "server": "plugin:io-guard:io",
        "tool": "hook.pre_tool_use",
        "input": {
          "hook_event_name": "${hook_event_name}",
          "session_id": "${session_id}",
          "tool_use_id": "${tool_use_id}",
          "prompt_id": "${prompt_id}",
          "tool_name": "${tool_name}",
          "cwd": "${cwd}",
          "scratchpad_dir": "${scratchpad_dir}",
          "transcript_path": "${transcript_path}",
          "permission_mode": "${permission_mode}",
          "agent_id": "${agent_id}",
          "tool_input": "${tool_input}"
        }
      }]
    }],
    "SessionStart": [{
      "hooks": [{"type": "command", "command": "sh \"${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh\" session_start"}]
    }],
    "UserPromptSubmit": [{
      "hooks": [{"type": "command", "command": "sh \"${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh\" heartbeat"}]
    }]
  }
}
```

PostToolUse and PostToolUseFailure bind the same way to `hook.post_tool_use` and
`hook.post_tool_use_failure`, with `"tool_response": "${tool_response}"` and `"error": "${error}"` added to the
map, and their matchers leave `io.run` out. The PreToolUse matcher names `io.run`'s callable name, so
`run.rules` holds it to the user's Bash and PowerShell rules (task 25). The hook on the plugin's own tool fires,
and its `ask` brings up the permission prompt although `--allowedTools` allowed the tool (`context.md`, "Hooks
and MCP", row 36).

An Edit or Write that Claude Code rejects as a `<tool_use_error>`, such as an `old_string` it cannot find, fires
no hook at all (`context.md`, "Hooks and MCP", row 30). The transcript still records the call and its error.
So at the session's next hook, `diagnose.refused` reads the transcript's last 256 KB from `transcript_path`,
takes the refusals after the last call that ran, and answers each once, before the model tries again (D28).

`hooks.bridge.call` receives the map, runs `run_event` with `Surface.MCP_HOOK`, which reads it through
`Event.from_fields`, and returns the answer JSON as the tool's text content. The harness reads that text exactly
as it reads command-hook stdout, and a `deny` in it blocks the call. The tool never sets `isError`, because an
error result produces a hook notice on every call. A `GUARD_ERROR` answers `{}` and warns once through
`user_message`. `scripts/server.py` starts `mcp.server`, which serves the hook tools, `hook.ping` and the io
tools (section 7).

A session runs several processes: the server, and a command hook at SessionStart and at each UserPromptSubmit.
Their `SessionState` shares its warned keys through `sessions/<session>.warned` in the plugin data folder, under
`file_lock`, so a check that breaks on SessionStart and on tool events warns once in all of them.

Task 03 checked this path live on Windows with Claude Code 2.1.283 (`context.md`, "Hooks and MCP"):

- **Substitution gives strings.** `${tool_input}` becomes the compact JSON text of the whole object. A number
  becomes its digits, a boolean `true` or `false`, and an absent field an empty string. A multi-line `content`
  with quotes, backslashes and non-ASCII arrives exact. A literal number or boolean written into `input` keeps its
  type.
- **The answer is the decision.** A `deny` returned as the tool's text blocked a Bash call, and the model saw the
  reason as `PreToolUse:Bash hook error: <reason>`.
- **It is fast.** Ten calls took 1.4 ms at p50 and 3.9 ms at p95, against 58.3 ms and 74.7 ms for an exec-form
  command hook that starts Python.
- **A hook-invoked tool never prompts**, even when the same tool called by the model would.
- **A dead server fails open.** A server that exits is restarted on the next hook call, in about 50 ms. One that
  cannot start gives the non-blocking notice `MCP server "plugin:io-guard:io" is not connected`, the tool call
  runs, and the model sees nothing. The server-down warning therefore comes from the heartbeat hook, never from
  the bridge.
- **SessionStart cannot use it.** The docs say `mcp_tool` hooks are skipped at launch, before the servers
  connect, so SessionStart stays a command hook.
- **The rest of the map substitutes the same way** (task 08). `${tool_response}` is the compact JSON text of the
  tool's output object, `${error}` the failure's text, and a Write of 145,599 bytes arrived whole.

The bridge pays off in three ways. No Python starts per call. The profile cache, the git status cache, the
read set and the probe live in one process. Fail-open comes from the harness, which continues on a
disconnected server. The cost is the two risks in `review.md`, holes 3 and 4, and section 8 answers them.

### The launcher across Windows and macOS

Only two things start Python. The server starts from `.mcp.json`, and the SessionStart and heartbeat hooks
start from `scripts/hook.sh`. The command entry point `hook.py` serves those two hooks and the CLI.

```json
{
  "mcpServers": {
    "io": {
      "command": "${user_config.python}",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/server.py"],
      "env": {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "IOGUARD_DATA": "${CLAUDE_PLUGIN_DATA}"}
    }
  }
}
```

`plugin.json` declares `userConfig.python` with the default `python3`, the title "Python interpreter" and the
description "The command that starts Python 3.14 or later. Windows with python.org Python: python". A user
changes it once with `/plugin configure io-guard`. The default suits macOS, where the Command Line Tools
provide `python3` and no `python`.

`hook.sh` is POSIX sh, started as `sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" <event>` so it needs no
executable bit. It runs under Git Bash on Windows and `sh` on macOS, which are the same two places the Bash
tool exists, and it uses only shell builtins. It resolves an interpreter with `command -v` in the order
`$CLAUDE_PLUGIN_OPTION_PYTHON`, which is the user's setting, then `python3`, `python` and `py -3`. It skips any
path under `WindowsApps`, runs `hook.py` with the event name, and on no interpreter prints a `systemMessage`
naming the fix and exits 0. On `session_start`, `hook.py` checks that its own Python and the one the server
starts from are both 3.14 or later, and a failed check is the session's one warning, again a `systemMessage`
that names the setting and the fix. A Windows machine without Git Bash runs shell-form hooks through
PowerShell, where the launcher does not run. That machine has no Bash tool either, and the `mcp_tool` hooks
still guard PowerShell, Edit and Write.

Every tool event goes through the `mcp_tool` hooks, and no command-hook fallback ships. Every release from
2.1.281, the minimum, runs `mcp_tool` hooks (`docs/compat.md`). A fallback would also have nowhere to live: a
snippet in the user's settings cannot name `${CLAUDE_PLUGIN_ROOT}`, and `/hooks` is read-only, so it cannot
switch the plugin's own hooks off.

## 7. Serve the io tools

### The dual-era dispatcher

`mcp.server` reads newline-delimited JSON-RPC from stdin as bytes, hands each message to `protocol.dispatch`
and writes each response through one lock. `protocol` decides the era per process.

```python
class Era(Enum):
    UNDECIDED = 0
    LEGACY = 1      # after initialize
    MODERN = 2      # after the first request with _meta protocolVersion

class Protocol:
    def dispatch(self, message: Mapping[str, Any]) -> Optional[Mapping[str, Any]]: ...
    def era(self) -> Era: ...
```

The rules of the dispatcher are these.

- `server/discover` answers in any era with `supportedVersions` `["2026-07-28", "2025-11-25"]`, the
  capabilities, `serverInfo`, `ttlMs` and `cacheScope`. It never changes the era.
- `initialize` sets `LEGACY` for the process and negotiates `2025-11-25` or `2025-06-18`. Every later request
  runs under legacy semantics, and `_meta` is optional.
- A request that carries `_meta["io.modelcontextprotocol/protocolVersion"]` while the era is `UNDECIDED` sets
  `MODERN`. A modern request missing `protocolVersion` or `clientCapabilities` gets `-32602`. An unsupported
  version gets `-32022` with the supported list.
- A modern result carries `resultType` and `_meta["io.modelcontextprotocol/serverInfo"]`. A legacy result
  carries neither.
- A tool execution error is a result with `isError: true`, `structuredContent` holding the `Result`, and its
  rendered text. A protocol error is a JSON-RPC error. Server-defined codes stay outside `-32768` to `-32000`.
- Unknown methods get `-32601`. A malformed line gets `-32700` and the loop continues.

The legacy path is the one Claude Code uses with a stdio server today, so it is built and tested first, and
the modern path is tested from recorded requests until a client sends them.

### The tool registry

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str                         # "io.edit"
    title: str
    description: str                  # what it does and when to use it, for tool search
    input: Optional[type]             # a dataclass, fields become inputSchema. None for a hook tool
    output: Optional[type]            # a dataclass, fields become outputSchema. None for a hook tool
    read_only: bool
    destructive: bool
    idempotent: bool
    handler: Callable[[Any, ToolCall], Any]
    open_world: bool = False          # io.run's openWorldHint
    max_result_chars: int = 80_000    # past it, the whole result goes to a file the answer names
    # ui: "ui://io-guard/dashboard" arrives with task 33, and handle_lifetime with task 25

class ToolCall:                                           # the context, built on first use, and the cancel token
    context: Context
    cancel: CancelToken
    cwd: Path                                             # the project, from CLAUDE_PROJECT_DIR
    spill: Optional[Path]                                 # the folder a long result is saved in
    session: str                                          # CLAUDE_CODE_SESSION_ID, for telemetry, task 38
    traceparent: Optional[str]                            # from the request's _meta, task 38
    tool_use_id: Optional[str]                            # _meta claudecode/toolUseId, context.md row 38

class ToolRegistry:
    def register(self, spec: ToolSpec) -> None: ...
    def list(self) -> list[dict]: ...                    # tools/list entries, in registration order
    def call(self, name: str, arguments: Mapping[str, Any], call: ToolCall) -> dict: ...
    def markdown(self) -> str: ...                       # the skill's tool table, hook tools left out, task 27
```

A hook tool takes the map an `mcp_tool` hook sends and returns its MCP result as it is. A bug in one answers
`{}`, so the call it guards goes on with no hook notice. A bug in an io tool answers a `GUARD_ERROR` tool
error, and arguments that do not fit the input schema get `-32602`, as do arguments a handler finds do not
make one call, which it raises as `InvalidArguments`.

`toolspec.schema(dataclass)` generates JSON Schema 2020-12 from the dataclass fields and their type hints:
`str`, `int`, `bool`, `Path` as string, `Optional`, `Sequence` and nested dataclasses. Every output schema
sets `additionalProperties: true`, because the client validates `structuredContent` against it and a strict
schema turns a new field into a failed call. `annotations` come from the three booleans plus
`openWorldHint: false`, and `io.run` sets `openWorldHint: true`. The callable name the model sees is
`mcp__plugin_io-guard_io__io_edit`, because the harness replaces the dot, and every fix text uses that name.

Each tool is one module with its input and output dataclasses, its `ToolSpec` and its handler. The handler
takes the input dataclass and a `ToolCall` holding the `Context`, the `CancelToken` and the
`ProgressReporter`, and returns the output dataclass. The `hook.*` tools are registered last, with the
description "Called by Claude Code hooks. Not for the model."

`markdown()` gives the skill page its tool table, and `mcp/skill.py` writes it and the code table from `CODES`
between the page's marker lines, run as `python tools/skill.py`. A test fails while the shipped page differs,
so a new tool or code ships with its row (task 27).

### Run a program, and read its log

`mcp/tools_run.py` holds `io.run`, `io.status` and `io.read_log` (task 25).

```python
io.run(argv = [], lang = "", code = "", cwd = "", env = {}, timeout_s = 0, background = False)
io.status(handle)
-> RunOutput(command, state, exit, ok, meaning, duration_s, log_path, log_bytes, errors, tail, handle, note)
io.read_log(path, since_line = None) -> LogOutput(path, first_line, last_line, text, dropped, more, note)
```

- **The user's rules hold first (D14).** `hooks.json` runs the PreToolUse hook on `io.run` too, where
  `run.rules` reads the Bash and PowerShell deny and ask rules of every settings file Claude Code reads, and
  meets them with the command the call runs, as `lib.rules` says. A deny rule refuses with `RULE_DENIED`. An
  ask rule answers `ask` with `RULE_ASKED` as the reason, so Claude Code shows its own permission prompt, and
  records the call's `runs.key` in the session. `io.run` checks again: a deny rule refuses, and an ask rule's
  command runs only when the hook recorded it, once. Elicitation cannot carry the question, because no
  surface shows its form (section 7, "Elicitation in both eras").
- **No shell.** `argv` runs as given. A `code` body is written byte for byte to `runs/<id>/body.<ext>` in the
  plugin data folder, a PowerShell body with a UTF-8 BOM for Windows PowerShell, and runs with
  `runs.interpreter` for its `lang`: the probe's Python, bash, pwsh or Windows PowerShell, or node. The
  program starts in `cwd` with the session's variables, `session.probe`'s UTF-8 ones over them and the call's
  `env` over both, an empty stdin, and stdout and stderr in `runs/<id>/output.log`.
- **To its end, or in the background.** A run to its end waits up to `timeout_s`, or `io.run.timeout_s`,
  sends `notifications/progress` when the request carried a `progressToken`, and is stopped, its whole
  process tree, past the timeout or on the client's cancel. A background run answers at once with a handle,
  which `io.status` reads. Either result is labelled by `shell.results`' options: a nonzero exit that
  `benign_exits` names is `ok` with its meaning, `error_patterns` pick the error lines, and the log's last
  `tail_lines` follow.
- **`io.read_log`** returns the whole lines a log gained since the last call, from the line and byte the
  session keeps per log, less the lines a `noise_patterns` regex matches. A half-written last line waits for
  its line break, `since_line` starts after a given line, a log shorter than the last call's byte starts
  over, and past `io.read_log.max_lines` the result says more lines wait.

### Batch edit, splice and append

`mcp/tools_edit.py` holds the three tools that change a file, and they share one path from the read to the
write (task 24).

```python
io.edit(path, edits: [{old_string, new_string}], expect_hash = "")
io.splice(path, start, end, text, include_end = False, expect_hash = "")
io.append(path, text, wrap_column = None, date_prefix = False, expect_hash = "")
-> ChangeOutput(path, profile, changed, lines: [{first_line, last_line}], sha256, indented, note, bytes)
```

1. **Hold the file.** `paths.LockTable` holds it against the server's other workers, then `lib.locks.file_lock`
   against every other io-guard process, each for up to `io.edit.wait_ms`, past which the call answers
   `FILE_LOCKED` (section 8).
2. **Load it.** A missing file is `PATH_NOT_FOUND`, one past `io.edit.max_bytes` `READ_TOO_LARGE`, a read-only
   one `READ_ONLY`, and one whose SHA-256 is not `expect_hash` `STALE_VIEW`. A binary file, or one whose bytes
   do not decode and encode back the same in `Profile.codec`, is `ENCODING_INVALID`.
3. **Change the text in memory.** `lib.edits` finds each place in the LF view the Edit tool reads, and makes
   the change in the file's own text. Every ending outside the change stays, each new line break takes
   `Profile.new_eol`, and new text indented the other way from the lines around it takes their style, which
   the result's `indented` names. `io.edit` makes its edits in order, each `old_string` found exactly once in
   what the edits before it left. `io.splice` replaces what lies between a unique `start` and the first `end`
   after it. `io.append` adds lines after the last one, dated after any list marker when asked, and wrapped at
   `wrap_column`, or at the `.editorconfig` `max_line_length` when none is given.
4. **Write once.** The text goes back in the file's encoding and BOM, through `write_atomic`, only when a byte
   changed. A write another program blocks is `FILE_LOCKED`, naming the holder.

A place that does not match once refuses the whole call, and nothing is written (ANC-3). The refusal is task
20's diagnosis, through `checks.diagnose.Diagnosis` with a `Wording` that names the tool's own argument and
callable, on the text the earlier edits left rather than the file. Its fix is the whole `io.edit` call again
with that edit corrected, and it never offers `replace_all`, which the io tools lack. Every result carries
"The built-in Edit tool needs a fresh Read of this file before its next use", because Claude Code tracks its
own tools' reads and writes only. `io.read` returns the `sha256` that `expect_hash` compares, which a caller
passes only when the rest of the file must be as it read it: in `live-edit-parallel` models passed each
result's hash on unasked, and the other subagents' writes refused them. Steps 1, 2 and 4 live in
`mcp/in_place.py`, which `io.format` shares.

### Format the changed lines

`mcp/tools_format.py` holds `io.format` (task 26).

```python
io.format(paths, lines = [])
-> FormatOutput(files: [FormattedFile(path, formatter, asked, reason, changed, lines, left, profile, sha256,
                                      bytes)],
                note)
```

1. **Hold every file.** Each path is held as the edit tools hold one, in the order of `paths.resolved`, so two
   calls that name the same files never wait on each other in a circle.
2. **Pick the lines.** `lines`, which goes with one path only, names them. Otherwise `GitPort.changed_ranges`
   gives the lines `git diff -U0 HEAD` reports, staged or not, and a file git has no commit of counts whole. A
   file with no changed line, or no format command for its extension, is left as it is, and its result says
   why.
3. **Format in memory.** The command from the `format` key runs with no shell in the file's folder, the file's
   text on stdin with every CRLF read as LF, and one `--lines`-style argument per range. A command that cannot
   start, exits nonzero, runs past `io.format.timeout_s`, or prints nothing for a file that holds text is
   `FORMAT_FAILED`, with the formatter's own message, and no file is written.
4. **Land it in the file's bytes.** `lib.edits.carried` matches the output to the file line by line. A line the
   formatter left keeps its own ending, a changed line takes `Profile.new_eol`, and the file keeps its BOM and
   encoding, whatever `LineEnding` the formatter's config names (BYT-3). A run of changes that meets none of the
   asked lines stays as the file had it, and the result names it in `left` (BYT-12).
5. **Write each file once**, only when a byte changed, after every file has been formatted.

Over 12 C++ files copied from one of the lead's projects, 8 CRLF and 4 LF, each given one new badly formatted
line and one line with doubled spaces, `io.format` wrote the same bytes as the script agents there ran 128
times to format changed hunks, with the same clang-format (`context.md`, task 26).

### Handles

```python
@dataclass(frozen=True)
class Handle:
    id: str              # UUIDv4
    kind: str            # "run" or "snapshot"
    created: datetime
    expires: Optional[datetime]   # None while the work it names still runs
    payload: Mapping[str, Any]

class HandleStore:
    def create(self, kind: str, payload: Mapping[str, Any]) -> Handle: ...
    def get(self, id: str, kind: str) -> Handle: ...      # raises HandleExpired
    def settle(self, id: str, ttl: timedelta) -> None: ...   # the work ended, so it expires ttl from now
    def close(self, id: str) -> None: ...
    def sweep(self) -> int: ...
```

Task 25 built the store with `io.run`, the first tool that hands out a handle, as `handles.STORE`, one per
server. A run handle lives in memory, so it ends with the server while its log stays on disk, and it
expires `io.run.handle_ttl_s`, one hour, after its program ends: the run's `Pump` calls `settle` when it sees
the end. Task 32 adds `${CLAUDE_PLUGIN_DATA}/handles/<id>.json` for a snapshot handle, which survives a server
restart and expires after seven days. Each tool description states the lifetime. `HandleExpired` becomes a
tool execution error `HANDLE_EXPIRED` whose fix names the creating tool.

### Elicitation in both eras

```python
class Elicitor(Protocol):
    def ask(self, form: Form, call: ToolCall) -> Union[Answer, Pending]: ...

class LegacyElicitor:   # sends elicitation/create, blocks the worker until the reply or the timeout
class ModernElicitor:   # returns Pending, and the tool answers resultType input_required with requestState
```

A tool that needs the user calls `call.elicit(form)`. Under `LEGACY` the worker thread sends
`elicitation/create` to the client and waits on an `Event` that the reader thread sets when the reply
arrives, with a timeout of five minutes. Under `MODERN` the tool returns `Pending`, the dispatcher answers
`resultType: "input_required"` with the form and a `requestState` that encodes the tool name, the arguments and
the step reached, and the retry with `inputResponses` resumes from that state without any memory in the
server. URL mode exists on 2026-07-28 connections only.

Task 03 found that no probed surface shows the user a form (`context.md`, "Hooks and MCP", row 16). The desktop
Code tab on 2.1.281 declines a legacy request without showing it, and `claude -p` cancels it. A modern
connection never answers a server-sent `elicitation/create`, so `ModernElicitor` is the only way to ask there.
A user decision therefore goes through a PreToolUse hook on the io tool's own call: the bridge answers `ask`,
and the harness shows its permission prompt, which the desktop does render. That covers a locked file, a restore
over newer edits, and an ask rule matched by `io.run`. No elicitor is built yet, because no tool needs one and
no surface shows its form. It arrives with a client that shows forms, where a declined or cancelled answer is a
refusal that names the decision.

### Progress and cancellation

`CancelToken` is a `threading.Event` per request id that the reader thread sets on `notifications/cancelled`.
Every loop in a long tool checks it, and a call cancelled before or while its tool runs answers a result with
`isError: true` and the code `CANCELLED`. `ProgressReporter` sends `notifications/progress` when the request
carried `progressToken` in `_meta`, at most twice per second, and `io.run` reports each run to its end through
it (task 25). The reader passes `dispatch` the writer's `send`, and `Protocol.call` builds each call's reporter
from it. A background run keeps running when its call is cancelled, because its handle owns the process.

### The ui resource

`resources/list` returns `ui://io-guard/dashboard` with `mimeType` `text/html;profile=mcp-app`, and
`resources/read` returns `ui/dashboard.html`. `io.dashboard` carries `_meta.ui.resourceUri` on its `tools/list`
entry, and `server/discover` lists `io.modelcontextprotocol/ui` in `extensions` with the same MIME type. The
tool's `structuredContent` holds counts and percentiles only, and the page fetches details through
`io.dashboard` with `scope: "details"`, which the page calls and the model does not. `tools/report.py --html`
renders the same template with the data inlined.

## 8. Share the process safely

The server is one process per Claude Code session, shared by the main conversation and every subagent (D13).
Two sessions on one project are two servers, so the process is thread-safe inside and every file it shares with
another server is safe across processes.

| Thread | Does | Never does |
|---|---|---|
| reader | reads stdin, parses, answers every method but `tools/call` itself so their order holds, hands each `tools/call` to a worker, sets cancel events | run a tool or a check |
| writer lock | serialises `stdout.write` and `flush` | hold the lock across a tool |
| workers, 4 | run hook tools and io tools | block on another worker |
| a waiter per run, task 25 | waits on the run's process, whose stdout and stderr go straight to its log, and settles its handle when it ends | parse output |
| watchdog | writes the heartbeat file every 5 seconds, and marks it stopped at the end | anything on the request path |

Telemetry has no thread of its own. One lock in `Telemetry` serialises the appends, and each line is on disk
before `record` returns, so a crash loses none. `sys.stdout` points at stderr inside the server, so a stray
print cannot corrupt an answer.

Locks are few and named. `paths.LockTable.lock(path)` is one `threading.Lock` per resolved path, which
`io.edit`, `io.splice`, `io.append` and `io.format` hold from the read to the write, so two subagents editing
one file take turns. `io.format` takes several in the order of their resolved paths. Three subagents' 30
interleaved `io.edit` calls on one file all landed in `live-edit-parallel` (task 24). `SessionState` fields
are guarded by one `RLock`. Caches carry a TTL: git status 2 seconds, a file profile until its mtime and size
change, the probe for the session.

Across processes, three rules keep two servers from corrupting each other's work.

| Shared thing | Rule |
|---|---|
| A file an io tool edits | Inside the thread lock, the tool takes `lib.locks.file_lock(path)`: an exclusive lock on `${CLAUDE_PLUGIN_DATA}/locks/<sha1 of the resolved path>.lock`, or under the system temporary folder's `io-guard` with no data folder, through `msvcrt.locking` on Windows and `fcntl.flock` on macOS, held from the read to the atomic replace, with an `io.edit.wait_ms` wait of 5 seconds and then `FILE_LOCKED`. The write itself is a temp file in the same folder and `os.replace`, so a reader never sees half a file |
| Telemetry | One file per session, `events/<YYYY-MM>/<session>.jsonl`, so two servers never interleave lines. `tools/report.py` merges them |
| Config | Loaded once per process and read-only after that. `io.config` writes the project file atomically, and a running server picks the change up at its next start |

Snapshots and handles are keyed by id and written atomically, so two servers never write the same file.

What must never block: the reader, the writer under its lock, and a `hook.*` call. A hook tool answers within
the pipeline budget from cached state, and a stale cache refreshes on the watchdog after the answer. A git
call inside a hook tool has a 500 ms timeout and a cache miss counts as unknown, never as a refusal.

Crash safety has four parts. `dispatch` wraps every message in the fail-open boundary, so a bug answers `{}`
or an `isError` result and the loop continues. The reader answers a malformed line with `-32700` and reads on.
The watchdog writes `${CLAUDE_PLUGIN_DATA}/sessions/<session>.alive`, named by `CLAUDE_CODE_SESSION_ID` from
the server's environment, with its process, era and time (`context.md`, "Hooks and MCP", row 34). The
`server.heartbeat` check runs in a `UserPromptSubmit` command hook and warns once when the beat is older than
30 seconds with no clean stop. Claude Code restarts a server that exited on the next hook call, but one that
cannot start leaves every hook failing open and tells the model nothing (row 18). Worse, Claude Code then
records the failure in `~/.claude/mcp-needs-auth-cache.json` and skips the server in every session for 15
minutes (row 33). With no heartbeat for its session, the check reads that cache and names the skip and its
end. That hook is the only Python spawn per turn, and costs about 250 ms.

Shutdown is one ordered list: stop accepting, drain the workers with a 2 second cap, close the heartbeat. A
background run keeps running past the server's end, and its log stays in the plugin data folder. Telemetry
needs no flush, because each line is on disk before `record` returns.

## 9. Record telemetry

One JSONL line per decision or tool call, in `${CLAUDE_PLUGIN_DATA}/events/<YYYY-MM>/<session>.jsonl`, one file
per session as section 8 says.

```json
{"schema": 1, "ts": "2026-09-27T14:03:11.412Z", "session": "abc123", "project": "myproject",
 "platform": "win32", "surface": "mcp_hook", "event": "PreToolUse", "tool": "Bash",
 "check": "transport.body", "code": "BODY_MOVED_TO_FILE", "severity": "fixed",
 "latency_ms": 11.8, "fixed": ["BODY_MOVED_TO_FILE"], "skipped": [], "error": null,
 "tool_use_id": "toolu_01ABC", "agent_id": null, "prompt_id": "550e8400",
 "trace": {"trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "span_id": "00f067aa0ba902b7",
           "parent_span_id": null},
 "cmd_head": "python - <<'PY'", "file_ext": ".cpp", "bytes": 9312}
```

The schema holds no file content, no `old_string`, no `new_string` and at most 200 characters of a command.
`project` is the repository's basename. A `GUARD_ERROR` line carries the exception type and a hash of the
traceback, and the traceback itself goes to `debug.log` only when `telemetry.debug` is true.

`ToolRegistry.call` writes one line per io tool call (task 38): `surface` `mcp_tool`, `event` `tools/call`,
`tool` the io tool's name, `code` and `severity` of a refusal, `CANCELLED` or `GUARD_ERROR`, or null when the
call answered, `latency_ms`, `file_ext` of the call's `path` or first of its `paths`, and `bytes`, what the
call wrote to the user's files. The line's `tool_use_id` is the one Claude Code sends in the call's `_meta` as
`claudecode/toolUseId`, and its trace derives from it as a hook event's does, so an `io.run` call and its
PreToolUse decision share a trace. A hook tool writes none, because the pipeline records each hook call. A line
that cannot be written is logged, and the call answers as it would have.

Trace context follows W3C Trace Context. An MCP call takes `traceparent` from `_meta` when present. A hook
event derives `trace_id` from `tool_use_id`, so the PreToolUse decision, the io tool call and the PostToolUse
verification of one tool use share a trace, and `prompt_id` joins them to Claude Code's own OpenTelemetry
events. `tools/report.py` groups by `trace_id` to show what one tool use cost end to end.

`python tools/report.py [--data FOLDER ...] [--days 7]` (task 28) merges every session file of the days asked,
from each installed io-guard's data folder unless `--data` names one, and leaves out `io-guard-inline`, the
probes' folder. It prints one screen: the calls by event, tool, project and platform, the codes split into
fixed, warned and refused, the time of a hook call, an io tool call and one tool use across its trace as p50,
p90, p99 and max, the command shapes behind refusals, and each kind of `GUARD_ERROR` with its count. It holds
command shapes and error hashes, so it prints to a terminal. `Report.counts()` is what a tool result, such as
the dashboard's, may carry: counts and percentiles, and no command, path, project or error text.

## 10. Abstract the platform

```python
@dataclass(frozen=True)
class Platform:
    os: str                              # "win32" or "darwin"
    fs_case_insensitive: bool
    unicode_form: Optional[str]          # "NFC" on macOS, None on Windows
    reserved_names: frozenset[str]       # Windows device names, empty on macOS
    path_conversion: bool                # MSYS conversion applies to the Bash tool
    shell_for: Mapping[Tool, str]        # Tool.BASH -> "bash", Tool.POWERSHELL -> "pwsh"
    lock_lookup: str                     # "restart_manager" or "lsof"
    temp_dir: Path
    bash_version: Optional[tuple[int, int]]
    gnu_tools: bool                      # GNU sed and grep on PATH

def detect() -> Platform
```

`detect` runs once per process from `sys.platform`, `os.name`, a case probe that creates two files under the
data directory differing by case, and the tool versions the probe found. Every platform difference lives
behind a `lib` function that takes the `Platform`: `paths.normalise`, `paths.reserved`, `locks.holders`,
`proc.run`, `shell.dialect`. A check reads `ctx.platform` and `ctx.probe` and never `sys.platform`.

| Concern | Windows | macOS |
|---|---|---|
| Transport budget and halving | measured, adaptive | none, pending task 36 |
| Path conversion | `win_paths` on | `win_paths` off by `platforms` |
| Console encoding | cp1252 unless `PYTHONUTF8` | UTF-8 |
| Lock holders | Restart Manager through `ctypes` | `lsof -F pc` |
| Atomic write retry | `PermissionError` retried five times with backoff | one attempt |
| File names | case-insensitive, device names | case-insensitive on APFS by default, NFD |
| Shell dialect lint | bash 5 from Git Bash, PowerShell 5.1 and 7 | bash 3.2 or Homebrew bash, BSD tools |
| Launcher | Git Bash runs `hook.sh` | `sh` runs `hook.sh` |

## 11. Test at six levels

| Level | Question | Where | Runs |
|---|---|---|---|
| unit | Is the mechanism right on these bytes? | `tests/lib/` | CI on Windows and macOS runners, 3.14 and the newest release |
| check | Does this check decide right on this event? | `tests/checks/` with `Context.fake` | CI |
| pipeline | Do checks order, compose, stop, budget and fail open as specified? | `tests/checks/test_pipeline.py` | CI |
| hook | Does JSON in give the documented JSON out? | `tests/hooks/`, `hook.py` as a subprocess | CI |
| conformance | Does the server answer both eras from recorded requests? | `tests/mcp/`, `server.py` as a subprocess | CI |
| replay | What would each check have done to the recorded calls? | `tools/replay.py` over `corpus/` | local, before a rule ships |
| live | What does this harness really do? | `tools/probes/` and `docs/live-checks.md` | by hand, with the version recorded. Windows only while the lead's Mac is down (D21) |

Meta tests keep the suite honest. `test_meta.py` fails on a duplicate method name, on a code in `CODES` that no
test produces, on a registered check without a test module, on a `ToolSpec` whose output dataclass has no
`additionalProperties`, and on a fixture whose hash left `MANIFEST.sha256`. The fixed-point test runs every
recorded rewrite twice. The matrix uses `subTest` over CRLF, LF, mixed, lone CR, with and without a BOM, and
over both sides of every threshold.

Conformance drives the server through pipes with two scripts: `initialize`, `notifications/initialized`,
`tools/list`, `tools/call`, `elicitation/create` round trip, and `server/discover`, `tools/call` with `_meta`,
a call without `_meta`, a call with an unknown version, `input_required` and its retry. Each script is a JSONL
file under `tests/mcp/requests/` with the expected shape beside it.

Live checks are a checklist page, one row per harness fact the design leans on, with the platform, the
Claude Code version and the date of the last confirmation. Task 04 owns it.

### The replay corpus and report

`python tools/corpus.py NAME=FOLDER ...` reads each transcript folder, subagent transcripts included, and writes
`corpus/<NAME>.jsonl` and `corpus/index.json`. A `Record` is one Bash, PowerShell, Edit, MultiEdit, Write, Read,
Grep, Glob or NotebookEdit call: its tool use id, project, session, whether a subagent made it, time, Claude Code
version, cwd, permission mode, the whole input, whether it failed, the first 2,000 characters of the result and
its full length, the structured `toolUseResult` with strings cut at 4,000 characters and lists at 200 items, and
its labels from `cli.labels`. A resumed session copies its history into a new transcript, so one call can sit
in several files: each tool use id enters once, and `index.json` counts the skipped `copies`. `corpus/` never
leaves the machine (D8).

`python tools/replay.py` runs each record as a PreToolUse event, then as PostToolUse or PostToolUseFailure with
the recorded result, through `default_registry()`. A shell call recorded without its structured response
carries its result text as `stdout`. Each session gets an in-memory context: a file system that holds only the
output Claude Code saved for the call, read from disk while the file is still there, a clock that stands still,
telemetry off, and a git that answers from each repository's files as git tracks them now. Nothing runs but
one `git ls-files` per repository, nothing is written, and the budget never skips a check. A file created in a
session and committed later reads as tracked, so a refusal of a write that created it is a replay artifact.
The report goes to `reports/replay-<time>.json`, and its shape is fixed at schema 1:

```json
{"schema": 1, "corpus": "corpus", "projects": ["myproject"], "checks_run": ["transport.body"],
 "records": 178000, "unreadable": 0, "seconds": 140.2,
 "by_tool": {"Bash": {"ok": 95000, "failed": 2579}}, "by_label": {"unexpected-eof": 236},
 "checks": {"transport.body": {
   "fix": {"ok": 1200, "failed": 180}, "refuse": {"ok": 3, "failed": 40}, "warn": {"ok": 10},
   "events": {"PreToolUse": 1433}, "raised": 0, "labels": {"unexpected-eof": 201},
   "false_positive_candidates": 3,
   "samples": [{"id": "toolu_01", "project": "myproject", "tool": "Bash", "input": "python - <<'PY'",
                "reason": "TRANSPORT_BUDGET: ..."}]}}}
```

`fix` counts decisions with a rewrite, `refuse` the denials, and `warn` any other decision that says something,
each split by whether the recorded call ran (`ok`) or failed. `labels` counts the labels of the calls the check
acted on, which is what it would have caught. `samples` holds up to 20 refusals of calls that ran, drawn evenly
from the whole corpus with a fixed seed, for the review a rule needs before it ships. Task 31 reads this shape,
so a change to it raises `REPORT_SCHEMA`.

## 12. Extend it

Three kinds of extension, with a different answer each.

- **Policy in config.** Every project sets patterns, skip trees, noise patterns and check options in
  `io-guard.json`, and the user sets verify commands in `config.json` (D24). This is the intended extension
  point and it needs no code.
- **User-scope checks.** A directory `${CLAUDE_PLUGIN_DATA}/checks/` holds modules that subclass `Check` and
  declare `CHECK_API = 1`. The registry loads them only when the user config sets
  `extensions.user_checks: true`, and a module declaring another `CHECK_API` is skipped with a warning. The
  user wrote them on the user's own machine, so they run with the plugin's trust.
- **Project-scope code.** Never. A cloned repository must not execute code through the guard, and the same
  rule keeps `autoMode` out of project settings in the harness.
- **Third-party checks.** A separate plugin with its own hooks. Plugins share no imports, so a shared check
  goes upstream into this repository instead.

## 13. Version it

- Until 1.0, `plugin.json` has no `version` and installs track commits. From 1.0 on, releases are semantic
  version tags with release notes (D18).
- `CONFIG_SCHEMA` is an integer. A loader reads every schema it has ever shipped and migrates in memory. A
  file from a newer schema loads with a warning and unknown keys ignored, which is the one place unknown keys
  are not errors.
- `TELEMETRY_SCHEMA` is an integer in every line. `tools/report.py` reads every schema it has ever shipped.
- A code is append-only. Its name and meaning never change. A retired code keeps its `CodeSpec` with an
  `until` field, so old telemetry still renders.
- A check id is stable. A renamed check keeps its old id as an alias in config for two versions.
- `CHECK_API` gates user-scope checks.
- The harness compatibility matrix in `docs/compat.md` names, per feature, the Claude Code version that
  introduced it and the probe that confirms it. Features gate on the probe where a probe exists
  (`bashEditDiff`, `updatedToolOutput`) and on the version otherwise (the halving fix, when it lands).
- `supportedVersions` in `server/discover` lists the MCP revisions the server implements. A new revision is
  added beside the old ones, never in place of them.
- Python 3.14 is the floor (D15), and CI runs the floor and the newest release on both platforms.
- The minimum Claude Code version is 2.1.281, the oldest release every probe passed on (`docs/compat.md`).
  The docs name no first version for `mcp_tool` hooks that wait for their server, so the floor rests on the
  probes.

## 14. Draw it

Boxes, grouped, then arrows. Each has a one-line label.

Boxes, harness group:
- `Claude Code session`: the desktop app or the CLI, one process per session.
- `Bash tool`: runs a command through Git Bash or bash.
- `PowerShell tool`: runs a command through pwsh.
- `Edit and Write tools`: write files and feed checkpoints.
- `Read tool`: reads a file into context.
- `Hook runner`: fires PreToolUse, PostToolUse, PostToolUseFailure and SessionStart.
- `Permission layer`: rules, the prompt, the auto-mode classifier.
- `MCP client`: connects the io server, legacy handshake by default.
- `Model`: the agent choosing the next call.

Boxes, io-guard group:
- `hooks.json`: binds tool events to hook.* tools and SessionStart to hook.sh.
- `hook.sh`: finds Python and starts hook.py.
- `hook.py`: command entry point, stdin to stdout.
- `hooks.entry`: runs the pipeline for one event.
- `hooks.answer`: renders an Outcome into the event's JSON.
- `hooks.bridge`: rebuilds an Event from substituted fields.
- `Pipeline`: selects, orders, chains rewrites, holds the budget, fails open.
- `Registry`: the fifteen checks and their metadata.
- `Checks`: location, transport, bytes, stale, read, output.
- `lib`: profile, anchors, shell, paths, git, locks, proc, results, config, rules.
- `Context`: config, probe, platform, git, fs, clock, session, telemetry.
- `io server`: stdio JSON-RPC, dual era, four workers.
- `Protocol`: framing, _meta, era, errors.
- `ToolRegistry`: io.* and hook.* specs with generated schemas.
- `io tools`: read, edit, splice, append, run, status, read_log, format, snapshot, restore, compare, stage.
- `HandleStore`: run and snapshot handles with lifetimes.
- `Elicitor`: legacy request or modern input_required.
- `Telemetry`: JSONL events with trace context.
- `Heartbeat`: the alive file the watchdog writes.
- `Config`: defaults, user, project, project local.
- `Probe`: platform facts taken at session start.
- `Scratchpad`: moved bodies and run logs.
- `Plugin data`: config, probe, snapshots, handles, events, heartbeat.
- `Dashboard page`: the ui resource and the standalone HTML.
- `Skill`: codes, fixes and the tool for each job.

Arrows:
- `Model` to `Bash tool`, `PowerShell tool`, `Edit and Write tools`, `Read tool`: a tool call.
- `Claude Code session` to `Hook runner`: fires the event before and after each call.
- `Hook runner` to `hooks.json`: matches the event and the tool.
- `hooks.json` to `MCP client`: an mcp_tool hook names plugin:io-guard:io.
- `MCP client` to `io server`: tools/call hook.pre_tool_use with the substituted fields.
- `hooks.json` to `hook.sh`: SessionStart in shell form.
- `hook.sh` to `hook.py`: starts Python with the event name.
- `hook.py` to `hooks.entry`: the parsed event.
- `io server` to `hooks.bridge`: the flat field map.
- `hooks.bridge` to `hooks.entry`: the rebuilt Event.
- `hooks.entry` to `Pipeline`: run this event in this Context.
- `Pipeline` to `Registry`: select and order the checks.
- `Registry` to `Checks`: instantiate with options.
- `Checks` to `lib`: values in, values out.
- `Checks` to `Context`: read config, probe, git, fs, session.
- `Pipeline` to `hooks.answer`: the Outcome.
- `hooks.answer` to `Hook runner`: deny, ask with updatedInput, allow, or context.
- `Hook runner` to `Permission layer`: rules and the classifier judge the updated input.
- `Permission layer` to `Bash tool`: the approved command runs.
- `Checks` to `Scratchpad`: a moved body or a run log.
- `Checks` to `Telemetry`: one line per decision.
- `Model` to `MCP client`: an io.* call after ToolSearch.
- `MCP client` to `io server`: initialize, tools/list, tools/call, elicitation reply.
- `io server` to `Protocol`: parse, validate _meta, pick the era.
- `Protocol` to `ToolRegistry`: dispatch by name.
- `ToolRegistry` to `io tools`: the input dataclass and the ToolCall.
- `io tools` to `lib`: profile, anchors, atomic write, run.
- `io tools` to `lib.rules`: match argv against the user's Bash rules.
- `io tools` to `HandleStore`: create, get, close.
- `io tools` to `Elicitor`: ask the user.
- `Elicitor` to `MCP client`: elicitation/create or input_required.
- `io tools` to `Telemetry`: one line per call with traceparent.
- `io server` to `Heartbeat`: written every five seconds.
- `hook.py` to `Heartbeat`: read once per turn, warn when stale.
- `Config` to `Context`: loaded once, validated, merged.
- `Probe` to `Context`: read by every platform-dependent check.
- `Plugin data` to `Config`, `Probe`, `HandleStore`, `Telemetry`, `Heartbeat`: the durable folder.
- `Telemetry` to `Dashboard page`: counts and percentiles, details in the page only.
- `Dashboard page` to `io tools`: io.config and io.restore after the user confirms.
- `Skill` to `Model`: the code table and the callable tool names, generated from CODES and ToolRegistry.
