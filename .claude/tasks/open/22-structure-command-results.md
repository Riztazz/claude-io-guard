---
title: "Structure command results: exit codes, errors, long output and the learned budget"
stage: E
area: output
created: 2026-09-27
status: open
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
