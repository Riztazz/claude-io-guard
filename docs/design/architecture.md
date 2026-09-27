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
    ioguard/
      __init__.py                  PLUGIN_VERSION, CONFIG_SCHEMA, CHECK_API, TELEMETRY_SCHEMA
      lib/                         mechanism, functions and frozen dataclasses only
        bytesio.py                 read_bytes, write_atomic, size guard
        profile.py                 Profile, profile, target_profile
        anchors.py                 find, closest, unique_anchor, extend_right
        shell.py                   split, heredocs, inline_bodies, redirects, dialect, budget_length
        pwsh.py                    PowerShell parse through pwsh when present, tokens otherwise
        paths.py                   normalise, reserved, link_target, inside, same_file
        git.py                     Git, the GitPort implementation
        locks.py                   holders, file_lock
        proc.py                    run, Pump, background
        results.py                 CodeSpec, CODES, Code, Result, Fix, render
        config.py                  Config, SCHEMA, load, validate, merge
        events.py                  HookEvent, Tool, PermissionMode, Surface, Event
        context.py                 Context, the ports, SessionState, Probe
        decisions.py               Verdict, Rewrite, Decision, compose
        telemetry.py               Telemetry, TraceContext
        platform.py                Platform, detect
        text.py                    visible, snippet, wrap, head
        rules.py                   permission rules: load, match_argv
      checks/                      policy, one module per check
        base.py                    Check, CheckMeta, Cost
        registry.py                Registry, default_registry
        pipeline.py                Pipeline, Outcome, Budget
        session_probe.py           SessionStart
        location.py                OUTSIDE_WRITE_ROOT, LINKED_PATH, RESERVED_NAME, READ_ONLY
        transport_body.py          BODY_MOVED_TO_FILE, TRANSPORT_BUDGET, BACKSLASH_TRANSPORT
        shell_writes.py            SHELL_WRITE, scratch script warning
        lint.py                    quoting, escapes, dialect, PIPE_HIDES_EXIT
        win_paths.py               MSYS_PATH, device names, cmd quirks
        conform_write.py           EOL_CONVERTED, BOM_RESTORED
        conform_edit.py            TRAILING_WS_STRIPPED avoidance, INDENT_MISMATCH
        verify_write.py            profile drift after Edit and Write
        touched.py                 TOUCHED_BY_SHELL, new files
        read_profile.py            the profile line after Read
        diagnose.py                PostToolUseFailure branches
        command_results.py         EXIT_BENIGN, ERRORS_IN_OUTPUT, OUTPUT_SAVED, MOJIBAKE
        commit_policy.py           task 29
      hooks/
        entry.py                   run_event(raw) -> answer dict
        answer.py                  Outcome -> hook JSON, per event and rewrite mode
        bridge.py                  hook.* tools: substituted fields -> Event -> run_event
      mcp/
        server.py                  stdio loop, threads, shutdown
        protocol.py                framing, _meta, eras, JSON-RPC errors
        toolspec.py                ToolSpec, schema generation, tools/list
        handles.py                 HandleStore
        elicit.py                  Elicitor, LegacyElicitor, ModernElicitor
        progress.py                ProgressReporter, CancelToken
        tools_read.py              io.read
        tools_edit.py              io.edit, io.splice, io.append
        tools_run.py               io.run, io.status, io.read_log
        tools_format.py            io.format
        tools_history.py           io.snapshot, io.restore, io.compare, io.stage
        tools_dashboard.py         io.dashboard, io.config, the ui resource
        tools_hook.py              hook.pre_tool_use, hook.post_tool_use, hook.post_tool_use_failure, hook.ping
      cli/
        main.py                    probe, check, profile, codes, replay, report, serve, doctor
tests/                             mirrors ioguard, plus fixtures/, support/, mcp/, replay/
tools/                             ioguard.py, corpus.py, replay.py, measure.py, report.py, probes/
```

Three rules hold the layout together. `lib` imports only the standard library and other `lib` modules.
`checks`, `hooks`, `mcp` and `cli` import `lib` and never each other, except that `hooks.bridge` and
`mcp.tools_hook` call `hooks.entry`. `tools/` scripts import `ioguard.cli` and hold no logic.

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
    permission_mode: PermissionMode
    agent_id: Optional[str]
    surface: Surface
    raw: Mapping[str, Any]

    command: Optional[str]          # Bash and PowerShell, from tool_input["command"]
    file_path: Optional[Path]       # Edit, Write, Read, normalised once
    old_string: Optional[str]
    new_string: Optional[str]
    replace_all: bool
    content: Optional[str]

    @classmethod
    def from_hook_json(cls, raw: Mapping[str, Any], surface: Surface) -> "Event": ...
    @classmethod
    def from_fields(cls, fields: Mapping[str, str]) -> "Event": ...
```

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
    def changed_ranges(self, path: Path) -> tuple[LineRange, ...]: ...
    def attributes(self, path: Path) -> Mapping[str, str]: ...

class FsPort(Protocol):
    def read_bytes(self, path: Path, limit: Optional[int] = None) -> bytes: ...
    def write_atomic(self, path: Path, data: bytes) -> WriteReport: ...
    def stat(self, path: Path) -> Optional[FileStat]: ...
    def exists(self, path: Path) -> bool: ...
    def holders(self, path: Path) -> tuple[Process, ...]: ...

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
    console_encoding: str
    fs_case_insensitive: bool
    transport_budget: Optional[int]  # bytes, None where no cut exists
    halving: bool                    # the Bash tool halves backslashes
    claude_code_version: Optional[str]
    dirty_at_start: tuple[Path, ...]
    taken_at: datetime

class SessionState:
    read_hashes: MutableMapping[Path, str]      # sha256 of the bytes the agent last saw
    snapshots: MutableMapping[Path, Snapshot]    # profile and bytes before a write
    warned: MutableSet[str]                      # one user warning per key per session
    budget_override: Optional[int]               # learned from an EOF failure
    last_failed_build: Optional[datetime]

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

    @classmethod
    def live(cls, data_dir: Path, project: Path) -> "Context": ...
    @classmethod
    def fake(cls, **overrides: Any) -> "Context": ...
```

`Context.live` builds the real ports and loads the probe and the config from `${CLAUDE_PLUGIN_DATA}`.
`Context.fake` builds in-memory ports for tests, with a fake file system that takes a mapping of path to
bytes. A check receives a `Context` and reads it. No check writes into it except `session`, and only through
its typed fields.

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
    def render(self) -> str: ...     # "CODE: what happened. What to do."
```

`CODES` is the one declaration. The `Code` enum, the skill's code table, the telemetry vocabulary and the
meta test that demands one producing test per code all read it. The full list is the draft in `context.md`
plus `REWRITE_CONFLICT`, `BUDGET_EXCEEDED`, `HANDLE_EXPIRED`, `RULE_DENIED`, `RULE_ASKED`, `SERVER_DOWN` and
`CANCELLED`.

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
```

`target_profile(path, siblings, editorconfig, gitattributes)` returns the `Profile` a new file takes. Its
`sha256` is empty and its counts are zero.

## 3. Model a check

### The base class

```python
class Cost(Enum):
    CHEAP = 5          # estimated milliseconds, no IO beyond the event
    MEDIUM = 50        # reads files
    EXPENSIVE = 500    # runs a subprocess

@dataclass(frozen=True)
class ConfigKey:
    type: type
    default: Any
    doc: str
    project_may_set: bool = True

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

def default_registry() -> Registry:
    registry = Registry()
    for check_class in (SessionProbe, Location, TransportBody, ShellWrites, Lint, WinPaths,
                        ConformWrite, ConformEdit, VerifyWrite, Touched, ReadProfile,
                        Diagnose, CommandResults, CommitPolicy):
        registry.register(check_class)
    return registry
```

`register` validates at import: a unique id, every code in `CODES`, every `after` id known, every config key
typed, and `writes` empty when the check declares no rewrite. A test registers one class into an empty
registry to test a check alone. No import-time discovery, no decorators, one list.

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
8. **Merge.** The verdict is the maximum of the decisions. Context lines join in order. One
   `output_replacement` at most, from the first check that offers one.

Idempotence is a tested property, not a convention. `pipeline.run` on the input of a previous `Outcome` must
produce no rewrite and the same verdict. Every rewrite therefore recognises its own output: a moved body leaves
no heredoc, and CRLF content converts to CRLF unchanged.

## 4. Name the lib functions

Each module lists its public functions. Every one takes values and returns values.

```python
# bytesio.py
def read_bytes(path: Path, limit: Optional[int] = None) -> bytes
def write_atomic(path: Path, data: bytes, retries: int = 5) -> WriteReport
def would_collapse(before: int, after: int) -> bool

# profile.py
def profile(data: bytes) -> Profile
def target_profile(path: Path, siblings: Sequence[Profile], editorconfig: Mapping[str, str],
                   gitattributes: Mapping[str, str]) -> Profile
def convert_eol(text: str, eol: Eol) -> str
def with_bom(data: bytes, bom: Bom) -> bytes

# anchors.py
def find(data: bytes, anchor: bytes) -> AnchorMatch         # count, offsets, lines
def closest(data: bytes, anchor: bytes, limit: int = 3) -> tuple[Candidate, ...]
def unique_anchor(data: bytes, offset: int, minimum: int = 1) -> bytes
def extend_right(data: bytes, offset: int, length: int) -> int   # bytes to the next non-space

# shell.py
def split(command: str) -> tuple[Subcommand, ...]           # by && || ; | and newlines
def heredocs(command: str) -> tuple[Heredoc, ...]           # quoted flag, delimiter, body, span
def inline_bodies(command: str) -> tuple[InlineBody, ...]   # python -c, node -e, bash -c
def redirects(command: str) -> tuple[Redirect, ...]         # target, append, fd, is_device
def dialect(command: str) -> Dialect                        # BASH, POWERSHELL, MIXED
def budget_length(command: str) -> int                      # apostrophes count four
def move_body(command: str, body: Heredoc, file: Path) -> str
def has_halving_hazard(command: str) -> bool

# pwsh.py
def parse(command: str, pwsh: Optional[Path]) -> PwshParse  # errors, commands, arguments
def canonical(name: str) -> str                             # alias to cmdlet

# paths.py
def normalise(raw: str, cwd: Path, platform: Platform) -> Path
def reserved(path: Path) -> Optional[str]                   # "nul", "com1"
def link_target(path: Path) -> Optional[Path]               # junction or symlink
def inside(path: Path, roots: Sequence[Path], platform: Platform) -> Optional[Path]
def same_file(a: Path, b: Path, platform: Platform) -> bool

# git.py
class Git(GitPort): ...                                     # every call: -c core.quotepath=false, -z, timeout
def parse_status(raw: bytes) -> GitStatus
def parse_ranges(raw: bytes) -> tuple[LineRange, ...]

# locks.py
def holders(path: Path, platform: Platform) -> tuple[Process, ...]
def file_lock(path: Path, data_dir: Path, wait_s: float = 5.0) -> ContextManager[None]  # across processes

# proc.py
def run(argv: Sequence[str], cwd: Path, env: Mapping[str, str], timeout_s: float) -> RunResult
def background(argv: Sequence[str], cwd: Path, env: Mapping[str, str], log: Path) -> Pump
def interpreter_for(lang: str, probe: Probe) -> Optional[Sequence[str]]

# results.py
def spec(code: Code) -> CodeSpec
def render(result: Result) -> str
def render_many(results: Sequence[Result]) -> str

# config.py
def defaults() -> Config
def load(layers: Sequence[Path], registry_keys: Mapping[str, Mapping[str, ConfigKey]]) -> LoadReport
def validate(raw: Mapping[str, Any], scope: Scope) -> tuple[ConfigError, ...]
def merge(base: Config, over: Config) -> Config

# decisions.py
def compose(rewrites: Sequence[Rewrite], tool_input: Mapping[str, Any]) -> ComposeResult

# telemetry.py
class Telemetry:
    def record(self, event: TelemetryEvent) -> None
    def flush(self) -> None
def trace_from(tool_use_id: Optional[str], traceparent: Optional[str]) -> TraceContext

# platform.py
def detect() -> Platform

# text.py
def visible(text: str) -> str                 # tab, CR, BOM, private-use shown as markers
def snippet(data: bytes, line: int, around: int = 2) -> str
def wrap(text: str, column: int) -> str
def head(text: str, limit: int = 200) -> str

# rules.py
def load_rules(user_settings: Path, project_settings: Sequence[Path]) -> Rules
def match_argv(rules: Rules, argv: Sequence[str], tool: Tool) -> RuleMatch  # deny, ask, allow, none
```

## 5. Configure the policy

Policy data lives in `io-guard.json`. The file carries no comments, so its keys carry their meaning.

```json
{
  "schema": 1,
  "checks": {
    "transport.body": {"enabled": true},
    "win.paths": {"enabled": true, "prefixes": ["/Game/", "/Script/", "/Engine/"]},
    "verify.write": {"enabled": true, "ascii_only": [".md", ".py"]}
  },
  "transport": {
    "budget_bytes": 6000,
    "rewrite_mode": {"default": "ask", "acceptEdits": "ask", "plan": "ask",
                     "auto": "refuse", "dontAsk": "refuse", "bypassPermissions": "allow"}
  },
  "pipeline": {"soft_ms": 300, "hard_ms": 2000},
  "write_roots": {"extra": ["C:/Users/me/projs/unreal/UNREAL-SHARED"]},
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
key is a defect. The values above are the defaults the lead set on 2026-09-27.

**The rewrite mode is the user's (D12).** For each permission mode the user layer sets `refuse`, `ask` or `allow`.
In `refuse` the call is refused and the reason carries the corrected command, so the model reruns it and the
auto-mode classifier judges it. In `ask` the user sees the corrected command. In `allow` it runs at once and no
classifier sees it. `/plugin configure io-guard` cannot set nested keys, so the user edits `config.json`, calls
`io.config`, or uses the dashboard page, and the README shows each.

A project file restricts and never widens. It disables a check, adds `skip_trees`, `verify` commands and
`noise_patterns`, and narrows `budget_bytes`. It cannot add `write_roots.extra`, set `rewrite_mode` to
`allow`, or turn telemetry off. `ConfigKey.project_may_set` marks each check key. The scope rule exists
because a cloned repository must not be able to point writes outside itself or approve commands.

Loading happens once per process and fails loudly. `validate` reports an unknown key with the file, the key
and the nearest known key, a type mismatch with the expected type, and a scope violation with the layer that
may set it. A file with errors is dropped whole, the guard runs with the layers that loaded, and one
`user_message` names the file and the first error. Dictionaries deep-merge, lists replace, and a list key that
ends in `extra` appends.

## 6. Run the hooks

### The command entry point

`scripts/hook.py <event>` reads stdin as bytes, decodes UTF-8, builds `Event.from_hook_json`, calls
`hooks.entry.run_event`, writes one ASCII JSON answer to stdout and exits 0. Nothing else reaches stdout. A
crash before the answer is written prints `{}` and logs `GUARD_ERROR`.

```python
def run_event(raw: Mapping[str, Any], surface: Surface, ctx: Optional[Context] = None) -> dict:
    """Runs the pipeline for one hook event and returns the harness answer."""
```

`hooks.answer` turns an `Outcome` into the event's JSON. For PreToolUse the verdict and the rewrite mode decide
the shape.

| Outcome | Answer |
|---|---|
| OBSERVE, no rewrite | `{}` or `additionalContext` only |
| DENY | `permissionDecision: "deny"` with the rendered result as the reason |
| rewrite, mode `ask` | `permissionDecision: "ask"`, `updatedInput`, the note in `permissionDecisionReason` |
| rewrite, mode `allow` | `permissionDecision: "allow"`, `updatedInput`, the note in `additionalContext` |
| rewrite, mode `refuse` | `permissionDecision: "deny"` with the rewritten input as the `fix` |

The mode comes from `transport.rewrite_mode[permission_mode]`. File-tool rewrites from `conform_write` and
`conform_edit` always answer `allow`, because the harness auto-approves edits in the working directory in
every mode that matters. PostToolUse answers carry `additionalContext`, `classifierContext` and
`updatedToolOutput`. An `updatedToolOutput` has the tool's own output shape: for Bash, the `tool_response` object
with `stdout` replaced. A plain string there fails the harness's schema check and changes nothing.
PostToolUseFailure answers carry `additionalContext`. SessionStart answers carry `additionalContext` and write
`CLAUDE_ENV_FILE`.

### The mcp_tool alternative

The plugin's `hooks.json` binds every tool event to a tool on the plugin's own server. The server is the
scoped name `plugin:io-guard:io`, and the tools are `hook.pre_tool_use`, `hook.post_tool_use` and
`hook.post_tool_use_failure`.

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|PowerShell|Edit|Write|Read",
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
          "permission_mode": "${permission_mode}",
          "agent_id": "${agent_id}",
          "tool_input": "${tool_input}"
        }
      }]
    }],
    "SessionStart": [{
      "hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}\"/scripts/hook.sh session_start"}]
    }],
    "UserPromptSubmit": [{
      "hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}\"/scripts/hook.sh heartbeat"}]
    }]
  }
}
```

PostToolUse and PostToolUseFailure bind the same way to `hook.post_tool_use` and
`hook.post_tool_use_failure`, with `"tool_response": "${tool_response}"` and `"error": "${error}"` added to the
map.

`hooks.bridge` receives the map, calls `Event.from_fields`, runs `run_event` with `Surface.MCP_HOOK` and returns
the answer JSON as the tool's text content. The harness reads that text exactly as it reads command-hook stdout,
and a `deny` in it blocks the call. The tool never sets `isError`, because an error result produces a hook notice
on every call. A `GUARD_ERROR` answers `{}` and warns once through `user_message`.

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

The bridge pays off in three ways. No Python starts per call. The profile cache, the git status cache, the
read set and the probe live in one process. Fail-open comes from the harness, which continues on a
disconnected server. The cost is the two risks in `review.md`, holes 3 and 4, and section 8 answers them.

### The launcher across Windows and macOS

Only two things start Python. The server starts from `.mcp.json`, and the SessionStart hook starts from
`scripts/hook.sh`. The command entry point exists for the CLI and as the documented fallback.

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

`hook.sh` is POSIX sh. It runs under Git Bash on Windows and `sh` on macOS, which are the same two places the
Bash tool exists. It resolves an interpreter with `command -v` in the order `python3`, `python`, `py -3`,
skips any path under `WindowsApps`, runs `hook.py` with the event name, and on no interpreter prints a
`systemMessage` naming the fix and exits 0. A Windows machine without Git Bash runs shell-form hooks through
PowerShell, where the launcher does not run. That machine has no Bash tool either, and the `mcp_tool` hooks
still guard PowerShell, Edit and Write.

The fallback for a harness without `mcp_tool` hooks is a settings snippet in the README: the same event
groups as command hooks, shell form, calling `hook.sh <event>`. Hooks merge across settings levels, so the
snippet adds to the plugin's hooks and the user removes the plugin's `mcp_tool` entries by disabling the
plugin's `hooks` in `/hooks`.

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
    input: type                       # a dataclass, fields become inputSchema
    output: type                      # a dataclass, fields become outputSchema
    read_only: bool
    destructive: bool
    idempotent: bool
    handler: Callable[[Any, ToolCall], Any]
    ui: Optional[str] = None          # "ui://io-guard/dashboard"
    handle_lifetime: Optional[str] = None
    max_result_chars: Optional[int] = None

class ToolRegistry:
    def register(self, spec: ToolSpec) -> None: ...
    def list(self) -> tuple[dict, ...]: ...              # tools/list entries, fixed order
    def call(self, name: str, arguments: Mapping[str, Any], call: ToolCall) -> dict: ...
    def markdown(self) -> str: ...                       # the skill's tool table
```

`toolspec.schema(dataclass)` generates JSON Schema 2020-12 from the dataclass fields and their type hints:
`str`, `int`, `bool`, `Path` as string, `Optional`, `Sequence` and nested dataclasses. Every output schema
sets `additionalProperties: true`, because the client validates `structuredContent` against it and a strict
schema turns a new field into a failed call. `annotations` come from the three booleans plus
`openWorldHint: false`, and `io.run` sets `openWorldHint: true`. The callable name the model sees is
`mcp__plugin_io-guard_io__io_edit`, because the harness replaces the dot, and every fix text uses that name.

Each tool is one module with its input and output dataclasses, its `ToolSpec` and its handler. The handler
takes the input dataclass and a `ToolCall` holding the `Context`, the `CancelToken`, the `ProgressReporter`
and the `Elicitor`, and returns the output dataclass. `io.edit`, `io.splice` and `io.append` call
`lib.anchors`, `lib.profile` and `lib.bytesio`, and every result carries the line about a fresh Read before
the next built-in Edit. `io.run` matches its argv against the user's Bash and PowerShell rules through
`lib.rules` before it runs anything: a deny rule refuses with `RULE_DENIED`, and an ask rule elicits the
user's yes and refuses with `RULE_ASKED` when it cannot. The `hook.*` tools are registered last, with the
description "Called by Claude Code hooks. Not for the model."

### Handles

```python
@dataclass(frozen=True)
class Handle:
    id: str              # UUIDv4
    kind: str            # "run" or "snapshot"
    created: datetime
    expires: datetime
    payload: Mapping[str, Any]

class HandleStore:
    def create(self, kind: str, payload: Mapping[str, Any], ttl: timedelta) -> Handle: ...
    def get(self, id: str, kind: str) -> Handle: ...      # raises HandleExpired
    def close(self, id: str) -> None: ...
    def sweep(self) -> int: ...
```

Handles live in memory and in `${CLAUDE_PLUGIN_DATA}/handles/<id>.json`, so a snapshot survives a server
restart and a run handle does not. A run handle expires one hour after its process ends. A snapshot handle
expires after seven days. Each tool description states the lifetime. `HandleExpired` becomes a tool execution
error `HANDLE_EXPIRED` whose fix names the creating tool.

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
over newer edits, and an ask rule matched by `io.run`. An elicitor stays for a client that shows forms, and a
declined or cancelled answer is a refusal that names the decision.

### Progress and cancellation

`ProgressReporter` sends `notifications/progress` when the request carried `progressToken`, at most twice per
second. `CancelToken` is a `threading.Event` per request id that the reader thread sets on
`notifications/cancelled`. Every loop in a long tool checks it, and a cancelled tool returns a result with
`isError: true` and the code `CANCELLED`. A cancelled background run keeps running, because its handle owns
the process.

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
| reader | reads stdin, parses, enqueues, sets cancel and elicitation events | run a tool or a check |
| writer lock | serialises `stdout.write` and `flush` | hold the lock across a tool |
| workers, 4 | run hook tools and io tools | block on another worker |
| telemetry | drains a `queue.Queue` into the JSONL file, flushes every second and at exit | drop an event silently |
| pumps, per run | copy a child's stdout and stderr into its log | parse output |
| watchdog | writes the heartbeat file every 5 seconds, sweeps handles, refreshes the git status cache | anything on the request path |

Locks are few and named. `paths.LockTable.lock(path)` returns one `threading.Lock` per resolved path, held
across a read-profile-write sequence, so two subagents editing one file serialise. `SessionState` fields are
guarded by one `RLock`. Caches carry a TTL: git status 2 seconds, a file profile until its mtime and size
change, the probe for the session.

Across processes, three rules keep two servers from corrupting each other's work.

| Shared thing | Rule |
|---|---|
| A file an io tool edits | Inside the thread lock, the tool takes `lib.locks.file_lock(path)`: an exclusive lock on `${CLAUDE_PLUGIN_DATA}/locks/<sha1 of the resolved path>.lock` through `msvcrt.locking` on Windows and `fcntl.flock` on macOS, held from the read to the atomic replace, with a 5 second wait and then `FILE_LOCKED`. The write itself is a temp file in the same folder and `os.replace`, so a reader never sees half a file |
| Telemetry | One file per session, `events/<YYYY-MM>/<session>.jsonl`, so two servers never interleave lines. `tools/report.py` merges them |
| Config | Loaded once per process and read-only after that. `io.config` writes the project file atomically, and a running server picks the change up at its next start |

Snapshots and handles are keyed by id and written atomically, so two servers never write the same file.

What must never block: the reader, the writer under its lock, and a `hook.*` call. A hook tool answers within
the pipeline budget from cached state, and a stale cache refreshes on the watchdog after the answer. A git
call inside a hook tool has a 500 ms timeout and a cache miss counts as unknown, never as a refusal.

Crash safety has four parts. `dispatch` wraps every message in the fail-open boundary, so a bug answers `{}`
or an `isError` result and the loop continues. The reader survives a malformed line. The watchdog writes
`${CLAUDE_PLUGIN_DATA}/sessions/<session>.alive` with the time. A `UserPromptSubmit` command hook reads that
file once per turn and warns once when it is older than 30 seconds. Claude Code does not reconnect a stdio
server, so a dead server is a visible warning rather than a silent gap. That hook is the only Python spawn per
turn.

Shutdown is one ordered list: stop accepting, drain the workers with a 2 second cap, terminate background
runs whose handles asked for it, flush telemetry, close the heartbeat.

## 9. Record telemetry

One JSONL line per decision or tool call, in `${CLAUDE_PLUGIN_DATA}/events/<YYYY-MM>/<session>.jsonl`, one file
per session as section 8 says.

```json
{"schema": 1, "ts": "2026-09-27T14:03:11.412Z", "session": "abc123", "project": "CLICKER",
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

Trace context follows W3C Trace Context. An MCP call takes `traceparent` from `_meta` when present. A hook
event derives `trace_id` from `tool_use_id`, so the PreToolUse decision, the io tool call and the PostToolUse
verification of one tool use share a trace, and `prompt_id` joins them to Claude Code's own OpenTelemetry
events. `tools/report.py` groups by `trace_id` to show what one tool use cost end to end.

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

## 12. Extend it

Three kinds of extension, with a different answer each.

- **Policy in config.** Every project sets patterns, verify commands, skip trees, noise patterns and check
  options in `io-guard.json`. This is the intended extension point and it needs no code.
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
