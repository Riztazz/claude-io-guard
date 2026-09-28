---
title: Add run with an argument list under the user's rules, and log readers
stage: F
area: mcp
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [10, 22, 23]
findings: [OUT-2, OUT-8, OUT-10, OUT-11, RUN-2, RUN-4, RUN-6, SHW-2, SHW-4]
platforms: [windows, macos]
commit: "feat: run programs without a shell, under the user's rules, and read their logs in pieces"
---

## Why

49% of Bash calls run Python, and the shell string is where content gets mangled. A run tool that takes an
argument list, or a script body as a field, has no quoting layer at all, on either platform.

A run tool is also a way around the user's rules. Settings cannot match an MCP tool's arguments, so
`Bash(git push *)` in ask or deny never applies to `io.run(argv=["git", "push"])` unless the tool applies it (D14).

## What to build

- **`io.run(argv[] | {lang, code}, cwd, env?, timeout_s?, background?)`**
  - **Rule parity first (D14).** `lib.rules` loads the user and project permission rules, and `match_argv` matches
    the argv against the Bash and PowerShell rules before anything runs. A deny rule refuses with `RULE_DENIED`. An
    ask rule asks the user through the PreToolUse hook on the `io.run` call itself: the bridge answers `ask` with
    the matched rule as the reason, and the harness shows its permission prompt. Elicitation cannot carry it,
    because the desktop declines it without showing a form (`context.md`, "Hooks and MCP", row 16). `RULE_ASKED`
    is the refusal when the user says no.
  - Runs without a shell, through `lib.proc`.
  - A code body is written to a file under the scratchpad, then run with the platform's interpreter for its
    `lang`.
  - Task 10's UTF-8 defaults apply.
  - The full stdout and stderr go to a log file.
  - The result is `{exit, ok, log_path, errors[], tail[], duration_s}`, labelled by task 22's rules.
  - A background run returns a handle: an opaque UUIDv4, with its lifetime stated in the tool description, as the
    MCP guidance on stateful tools asks.
- **`io.status(handle)`**: reports on the process itself, never on its output file (RUN-2). An expired handle is a
  tool execution error, `HANDLE_EXPIRED`, that says how to start the run again.
- **`io.read_log(path, since_line?)`**: returns the lines added since the last call, minus `noise_patterns` from the
  config. It replaces `logcheck.sh`, which ran 83 times.
- **Moved here from task 23 with their first user:** `mcp/handles.py`'s `HandleStore` with `HANDLE_EXPIRED`
  (`architecture.md`, section 7, "Handles"), and `ProgressReporter` in `mcp/progress.py`, beside task 23's
  `CancelToken`, sending `notifications/progress` at most twice a second for a run that has a `progressToken`.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_run.py`, `lib/proc.py`, `lib/rules.py`, `tests/mcp/test_tools_run.py`.

## Done when

- Live on Windows: a 20 KB Python body holding `\\` runs byte-exact.
- Live on Windows: a 15-minute background run reports its status while it runs, and its final exit code when it
  ends.
- Live on Windows: with `Bash(git push *)` in the user's deny rules, `io.run(["git", "push"])` is refused, and with it
  in ask rules, the user is asked.
- The tests pass in CI on both platforms.

## Notes

- The Tasks extension (`io.modelcontextprotocol/tasks`) has no Claude client yet (`context.md`), so background runs
  use handles. Task 04's compatibility matrix tracks when a client declares it.
- **`noise_patterns` from a project file are regular expressions io-guard runs, and a cloned repository writes
  them.** Python's `re` has no timeout, so a pattern with nested repetition can stall a call for as long as the
  hook allows, 600 s by default. Bound them before `io.read_log` applies any: a length cap and a refusal of nested
  quantifiers at config load, or project patterns matched as plain substrings while only the user's own patterns
  are regexes. Raised with D24 on 2026-09-27, and the lead asked for it to be kept on record.
- **Task 22's `checks.shell.results.error_patterns` has the same exposure.** A project file may set it, and every
  Bash and PowerShell result runs its patterns in the io server. The guard built here covers both keys. Found on
  2026-09-28 during task 23.

## What changed

Checked on Windows 10 on 2026-09-28, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **`mcp/tools_run.py` holds `io.run`, `io.status` and `io.read_log`.** `io.run` takes `argv`, or `lang` and
  `code`, which it writes byte for byte to `runs/<id>/body.<ext>` in the plugin data folder and runs with the
  interpreter for its language: the probe's Python, bash, pwsh or Windows PowerShell, or node. The program
  runs with no shell, in `cwd`, with task 10's UTF-8 variables and the call's `env`, an empty stdin, and its
  stdout and stderr in `runs/<id>/output.log`. A run to its end is stopped, its whole process tree, past
  `timeout_s` or on the client's cancel. Its result is labelled by `shell.results`' options: a benign exit is
  `ok` with its meaning, and the error lines and the last lines come back. A background run answers a handle,
  and `io.status` reports the state from the process. `io.read_log` returns the whole lines a log gained since
  the last call, less `noise_patterns`.
- **Rule parity (D14):** `lib/rules.py` reads the Bash and PowerShell deny and ask rules of the managed, user,
  project and project local settings files, and matches them as Claude Code's permissions page describes,
  wrappers and `NAME=value` stripped, the program also by its bare name. The new check `run.rules` runs at the
  PreToolUse hook on `io.run`, now in `hooks.json`'s matcher: a deny rule refuses with `RULE_DENIED`, and an
  ask rule answers `ask` with `RULE_ASKED`, so Claude Code shows its own prompt, and records the call's key.
  `io.run` checks again, and runs a command an ask rule meets only when the hook recorded it, once.
- **`mcp/handles.py`'s `HandleStore`** holds run handles in memory, one hour past the program's end, which
  `lib.proc.Pump` settles when its waiter thread sees the end. `HANDLE_EXPIRED` names `io.run` as the fix.
  **`ProgressReporter`** sends `notifications/progress` at most twice a second when a request carried a
  `progressToken`, and `dispatch` takes the writer's `send` for it.
- **The regex guard (the notes above):** `lib/patterns.py` refuses a pattern that does not compile, is over 200
  characters, or repeats a group that repeats inside, and `ConfigKey.project_regex` applies it to a project
  file's `noise_patterns` and `checks.shell.results.error_patterns`. The user's own `config.json` may set any.
- **New codes:** `RULE_DENIED`, `RULE_ASKED` and `HANDLE_EXPIRED`. New keys: `io.run.timeout_s` of 120,
  `io.run.handle_ttl_s` of 3,600, `io.read_log.max_lines` of 500 and `noise_patterns`.
- **Choices made here:** `argv` and `lang` and `code` are flat fields, not an object. A body goes in the plugin
  data folder, because an MCP call carries no scratchpad path. Run handles stay in memory, as the design said,
  and the file per handle waits for task 32's snapshots. A background run keeps running past the server's end.
  io-guard does not map PowerShell aliases to cmdlets, which Claude Code does. A handler may raise
  `InvalidArguments`, which answers `-32602`.
- **Fixed in passing:** task 24 put its README paragraph in the middle of the io tools table, which split it.

Evidence:
- `python tests/run_all.py` ran 658 tests, all passing, against 623 after task 24. New: `lib/test_rules.py` 8,
  `lib/test_patterns.py` 3, `lib/test_runs.py` 2, `mcp/test_tools_run.py` 14, `mcp/test_progress.py` 2,
  `checks/test_run_rules.py` 3, and more in `test_proc.py` and `test_config.py`. The rule tests cover every row
  of the permissions page's wildcard table.
- `live-run-body` passes on 2.1.281 and 2.1.283: a 21,527-byte Python body with 500 pairs of backslashes
  reached `body.py` byte for byte, and Python printed `250 C:\\dir\\250`. The model's first try sent single
  backslashes, so the prompt now says both belong.
- `live-run-denied` and `live-run-asked` pass on both: `PreToolUse:mcp__plugin_io-guard_io__io_run hook error:
  RULE_DENIED: io.run would run git push origin main`, and for `git fetch --dry-run` the hook answered `ask`,
  the permission prompt tool received the call, and the approved run went through ("Hooks and MCP", row 36).
- `live-run-background` passes on both: a background run of 15 one-minute steps answered `running` at 0 s, and
  `io.status` said `running` at 2.1 and 2.2 s, then after a 16-minute pause `ended`, exit 0, 900 s, with
  `minute 14` as its last line. The sessions took 979 and 986 s. `run_probe.py`'s kill timer now allows for a
  probe's pauses.

Docs updated: `architecture.md` sections 1 to 8, with a new part on the run tools. The README's status, io tools
and settings. `compat.md` and `live-checks.md`. `context.md`: row 36 and a task 25 paragraph. `CLAUDE.md`'s
layout. The drawing's io tool flow, whose first step now names the rules at `io.run`'s hook.

Not checked:
- macOS, live or in CI until the lead pushes. Task 36 holds the macOS checks of `killpg` and the interpreters.
- A person answering the ask prompt in the desktop app. The probes answer it through `--permission-prompt-tool`.
- `io.read_log` and a cancelled run, live. Both are unit-tested on real processes and files only.
- Progress notifications reaching a person: no probed surface shows them ("Hooks and MCP", row 16).
