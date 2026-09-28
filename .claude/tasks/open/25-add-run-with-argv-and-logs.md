---
title: Add run with an argument list under the user's rules, and log readers
stage: F
area: mcp
created: 2026-09-27
status: open
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
