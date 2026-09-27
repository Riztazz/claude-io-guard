---
title: "Structure command results: exit codes, errors, long output and the learned budget"
stage: E
area: output
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-27
depends-on: [03, 08, 10]
findings: [OUT-1, OUT-2, OUT-3, OUT-5, OUT-7, OUT-10, VFY-7, SHW-4]
platforms: [windows, macos]
commit: "feat: label exit codes and summarise errors in every command result"
---

## Why

Command results waste the agent's time in four ways:

- 148 results were cut to "Output too large" and needed a second read.
- Exit code 1 from grep or diff stops a chain for no reason.
- Build and test failures hide behind pipes and filters.
- Mojibake from a cp1252 console gets copied back into files.

A fifth is a guess the guard itself makes. The 6,000-byte transport budget from task 10 is right on the lead's
machine, and each machine's command wrapper differs (#95653).

## What to build

A PostToolUse and PostToolUseFailure check on Bash and PowerShell. It adds `additionalContext`. It replaces the
output with `updatedToolOutput` only for output saved to a file. Task 03 confirmed the field for Bash when it is the
tool's own `tool_response` object with `stdout` replaced. A plain string fails the harness's schema check and
changes nothing (`context.md`, "Hooks and MCP", row 8). PowerShell's shape is not probed yet.

- **`EXIT_BENIGN`:** label exit codes that are not failures, such as grep 1 (no match), diff 1 (the inputs
  differ), and the documented codes of test runners.
- **`ERRORS_IN_OUTPUT`:** scan the full output for errors, with patterns anchored at the start of a line:
  compiler, MSBuild and UBT errors, Python tracebacks, and test failures. Report the counts and the first lines.
- **`OUTPUT_SAVED`:** when the result says `Output too large (41.2KB). Full output saved to: <path>`, read that
  file and add its error lines and its last 20 lines.
- **`PIPE_HIDES_EXIT`:** flag output that reports a failure while a pipe made the exit code 0.
- **Stale binary (VFY-7):** warn when a test or run follows a failed build in the same session.
- **`MOJIBAKE`:** detect runs of U+FFFD and cp1252 artefacts, and give the encoding fix.
- **The learned budget.** When a command longer than 5 KB fails with "unexpected EOF while looking for matching",
  set `SessionState.budget_override` to its length minus one, and say that the command was too long for this
  machine's shell rather than badly quoted.

## Where

`plugins/io-guard/scripts/ioguard/checks/command_results.py`, `tests/checks/test_command_results.py`.

## Done when

- Replay over the 148 saved-output results, and over a sample of exit-1 results, gives each the right label.
- A summary line that only quotes an error word raises no alarm (OUT-7).
- Replay over the 125 unexpected-EOF commands lowers the budget only for the ones over 5 KB.

## What changed

Checked on Windows 10 on 2026-09-27, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **`checks/command_results.py`, `shell.results`.** After each Bash and PowerShell call it reads the output once:
  `error` after its `Exit code N` line for a failure, `stdout` and `stderr` for a call that ran, and the saved
  file for an output Claude Code saved. `EXIT_BENIGN` labels an exit code that is an answer, such as grep's 1,
  when every command that can have set it gives that answer or cannot fail without a message, and says when it
  stopped an `&&` chain. `ERRORS_IN_OUTPUT` counts and quotes the error lines of an output past 50 lines or
  saved. `PIPE_HIDES_EXIT` names the errors behind a pipe's exit code 0. `OUTPUT_SAVED` replaces a saved output
  with its first and last 20 lines and its error lines, numbered, under the file's path. `MOJIBAKE` names U+FFFD
  and UTF-8 read in cp1252 or cp1250, with the fix for each. `STALE_BINARY` warns on a run of what a failed
  build made. A well-formed Bash command over 5,000 bytes that failed with unexpected EOF sets
  `budget_override` to its length minus one, with a `TRANSPORT_BUDGET` warning that the tool cut it.
- **Error lines are patterns from a line's start, grouped by kind,** so "0 Error(s)" and "Errors: 0" raise
  nothing (OUT-7). A command that only reads a file or a log, such as grep or tail, raises no error line at all,
  since its output quotes errors. Both lists, the answer codes, the builds and the runs are settings, and a
  project adds its own. Thirteen keys under `checks.shell.results`.
- **`lib/output.py`:** `exit_code`, `saved_path`, `error_lines`, `mojibake` and `excerpt`. **`lib/shell.py`:**
  `pipelines` and `exit_candidates`, which read `&&`, `||`, `;` and pipes outside `$( )` and give up on
  parentheses, braces, `if`, `case`, `!` and an assignment joined by `&&`. `matching` moved in from lint's
  `build_label`, its second caller.
- **Choices made here:** a budget learned this session applies where the probe found no cut, as on macOS, and
  brings `transport.budget_bytes` with it. The replacement drops `persistedOutputPath` and
  `persistedOutputSize`, because with them Claude Code shows it only as its 2 KB preview. EXIT_BENIGN reads Bash
  only. `SessionState.last_failed_build` holds the failed build's words, which the warning quotes.
- **Replay:** a shell call recorded without its structured response carries its result text as `stdout`, and
  the saved output is read into the in-memory file system while it is on disk.
- **Probes:** `command-output` records row 32, and `live-results` runs io-guard on two saved outputs, a grep in
  an `&&` chain and a traceback behind `| tail`.

Evidence:
- `python tests/run_all.py` ran 559 tests, all passing, against 509 after task 21.
- `run_probe.py verdicts`: `command-output` and `live-results` pass on 2.1.281 and 2.1.283, and `live-empty` and
  `live-touched` still pass on 2.1.283. In `live-results` the model read no saved file, and `shell.results`
  took 4.8 ms on a 38 KB saved output and 0.3 to 0.4 ms on the others.
- Done-when, saved output: 147 of the 148 records are saved outputs, and one only prints the words. Replay
  replaced each of the 102 whose file is still on disk. The other 45 files were deleted with their sessions,
  a replay artifact, because live the file exists when the hook runs (row 32).
- Done-when, exit code 1: 47 of the 870 failures with exit code 1 got `EXIT_BENIGN`, and all 47, read in full,
  were right: grep, diff or a `[ ]` test whose answer ended the command or stopped its chain. In a sample of 40
  of the 870, the 4 labels were right, 35 were real failures left unlabelled, and 1 was missed, a PowerShell
  `Get-Process` that found nothing.
- Done-when, OUT-7: the tests `test_a_summary_line_that_quotes_an_error_word_raises_nothing` and
  `test_a_search_of_a_log_raises_no_alarm`. Of 40 `PIPE_HIDES_EXIT` results read from replay, each quoted a
  real exception or compiler error that `| tail`, `| head` or a formatter hid.
- Done-when, unexpected EOF: all 98 commands over 5 KB were well formed and 7,807 bytes or more as the budget
  counts them, and each lowered its session's budget. None of the 27 under 5 KB did.
- Replay over all 110,379 calls: `shell.results` warned on 732 calls that ran and 147 that failed, raised 0
  times, took 0.4 ms at p50, 1.4 ms at p99 and 121 ms on a 10.4 MB saved output. Every other check's counts
  match the replay before this task.

Docs updated: `architecture.md` sections 1, 2, 4, 5, 6 and 11. `context.md`: row 32 and a task 22 paragraph.
`live-checks.md` and `compat.md`. The README's status line, the grep example, which now shows a chain because
Claude Code already calls a lone grep with no match a success, a row in "What it fixes", the learned budget and
a "What a result means" setting. `CLAUDE.md`'s layout. The drawing still holds: its Checks box already names
the output concern, and it draws no step after a call.

Not checked:
- macOS, live or in CI until the lead pushes. Task 36 holds the macOS live check of the learned budget and of
  clang's error lines.
- `STALE_BINARY` in replay: the recorded builds run the projects' own build scripts, which the default `builds`
  list does not name, so replay produced none. Unit tests cover it, and task 30 names the projects' builds.
- A failed call's long output gets its error lines in context only, because PostToolUseFailure has no
  `tool_response` to replace.
- Replay's `ERRORS_IN_OUTPUT` count is low, because the corpus keeps only the first 4,000 characters of a
  result. Live calls bring up to 30,000.
