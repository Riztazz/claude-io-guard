---
title: Give each string-coded state a type
stage: I
area: runtime
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: enums for the states now spelled as strings"
---

## Why

Medium. A handful of states travel as plain strings, compared by literal at each reader, where an enum
would make a misspelling fail at once and let `match` check that every case is handled. The engineering skill:
a type for every identity, and never two id spaces sharing a primitive.

- `plugins/io-guard/scripts/ioguard/lib/rules.py:81`: `decision: str  # "deny", "ask", "unread" or "none"`,
  read by literal at `checks/run_rules.py:71,75`, `mcp/tools_run.py:172,174` and `lib/rules.py:336`, where
  the order `("deny", "ask", "unread")` is spelled once more.
- `plugins/io-guard/scripts/ioguard/lib/rules.py:90`: `dialect: str  # "bash" or "powershell", ""`, read at
  `checks/shell_writes.py:160` and `checks/commit_policy.py:62`.
- `plugins/io-guard/scripts/ioguard/lib/indent.py:12-17`: `style` returns `"tabs"`, `"spaces"`, `"mixed"` or
  `"none"`, while `lib/profile.py:45-49` has `IndentKind` with the same four members.
  `lib/edits.py:35` carries `indented: str | None  # "tabs" or "spaces"`, and
  `checks/conform_edit.py:78` compares `indent.style(new) == "mixed" and here in ("tabs", "spaces")`.
- `plugins/io-guard/scripts/ioguard/lib/code_tokens.py:101,109`: `how: str  # code, includes, or exact` and
  `MODES = ("code", "includes", "exact")`, checked by membership at `mcp/tools_history.py:291`.
- `plugins/io-guard/scripts/ioguard/mcp/tools_run.py:74`: `state: str  # running, ended, timed out or
  stopped`, set by literal at `tools_run.py:248-256,277`.
- `plugins/io-guard/scripts/ioguard/lib/heartbeat.py:20`: `era: str  # "undecided", "legacy" or "modern"`,
  while `mcp/protocol.py:39-42` has the `Era` enum, and `mcp/server.py:59,63,71` passes `era().value`.
- `plugins/io-guard/scripts/ioguard/hooks/answer.py:19`:
  `MODE_VERDICTS = {"refuse": Verdict.DENY, "ask": Verdict.ASK, "allow": Verdict.ALLOW}`, keyed by the same
  literals `lib/config.py:126` lists as `REWRITE_MODES`. A mode added to one and not the other is a `KeyError`
  in the hook.
- `plugins/io-guard/scripts/ioguard/lib/results.py:279`: `tool: str  # "Edit", "Write", "Bash", or a
  callable MCP name`, beside the `Tool` enum in `lib/events.py:28-36`.
- `plugins/io-guard/scripts/ioguard/checks/base.py:27`: `platforms: frozenset[str]  # sys.platform
  values`, and twenty-one checks spell `platforms=frozenset({"win32", "darwin"})`, while
  `lib/platform.py:9-10` names `WINDOWS` and `MACOS`. `lib/rules.py:60-61` keys `MANAGED` by the same
  literals.
- `plugins/io-guard/scripts/ioguard/cli/replay.py:37`: `KINDS = ("fix", "refuse", "warn")`, returned by
  `kind_of` as literals.

## What to build

- An enum per state: the rule decision, the shell dialect, the indent style (reuse `IndentKind`), the
  compare mode, the run state, the rewrite mode, and the replay kind. The heartbeat carries `Era`, and
  encodes its value only at the JSON boundary.
- `REWRITE_MODES` becomes the enum, and each member carries its `Verdict`, so `answer.MODE_VERDICTS` goes.
- `Fix.tool` takes a `Tool`, or the callable name, through a small union type, so a reader can tell which.
- One constant for every platform, such as `EVERY_PLATFORM = frozenset({WINDOWS, MACOS})`, or `platforms`
  defaults to it in `CheckMeta`, and the twenty-one copies go. `rules.MANAGED` keys by the constants.
- Each reader uses `match` over the enum where it branches, so a member left out is visible.
- A test that every `Tool` and every `PermissionMode` value round-trips, and one per new enum at its JSON or
  MCP boundary.

## Where

`lib/rules.py`, `lib/indent.py`, `lib/edits.py`, `lib/code_tokens.py`, `lib/heartbeat.py`, `lib/results.py`,
`lib/config.py`, `lib/platform.py`, `hooks/answer.py`, `checks/base.py`, every check's `CheckMeta`,
`checks/run_rules.py`, `checks/shell_writes.py`, `checks/commit_policy.py`, `checks/conform_edit.py`,
`mcp/protocol.py`, `mcp/server.py`, `mcp/tools_run.py`, `mcp/tools_history.py`, `cli/replay.py`,
`docs/design/architecture.md` section 2 for each type that changes.

## Done when

- No check module spells `"win32"` or `"darwin"`.
- A grep of `plugins/io-guard/scripts` for `== "deny"`, `== "bash"`, `== "mixed"` and `== "modern"` finds
  nothing.
- The suite passes.
