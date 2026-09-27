---
title: Catch quoting, escaping and dialect hazards before a command runs
stage: B
area: transport
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [08, 09, 11]
findings: [SHW-2, SHW-3, SHW-5, SHW-6, SHW-7, SHL-1, SHL-2, SHL-4, SHL-5, SHL-6, OUT-1]
platforms: [windows, macos]
commit: "feat: refuse commands whose quoting or dialect would change what runs"
---

## Why

Most shell failures are visible in the command text before it runs. Each one costs a round trip, and some change
what runs without an error. The baseline counts:

| Hazard | Count |
|---|---|
| Backtick failures | 2 |
| Trailing-backslash quotes | 17 |
| Python invalid-escape warnings | 72 |
| `unicodeescape` errors | 10 |
| PowerShell call operators sent to bash | 5 |

## What to build

A PreToolUse check on Bash and PowerShell, one rule per hazard. Every refusal carries a fix hint. A rule rewrites
the command only when the rewrite is mechanical, and every rewrite follows the rewrite mode from task 11 (D12).

- **`BACKTICK_IN_DOUBLE_QUOTES`:** backticks inside double quotes. Refuse, and suggest single quotes.
- **`TRAILING_BACKSLASH_QUOTE`:** a backslash right before a closing double quote in a path. Rewrite
  `"C:\x\"` to `"C:/x/"`.
- **`INLINE_SCRIPT_INVALID`:** compile each Python body, inline or moved, with `compile()` before it runs. Report
  a SyntaxError or a SyntaxWarning, such as an invalid escape or a `\U` inside a Windows path. Also flag
  `open(` without `encoding=`.
- **`DIALECT_MISMATCH`:** each shell's syntax sent to the other shell's tool.
  - PowerShell syntax in the Bash tool: the `&` call operator, `$env:`, `Get-*` cmdlets, here-strings.
  - Bash syntax in the PowerShell tool: `<<`, `tail`, `export`, and `&&` on Windows PowerShell 5.1.
- **PowerShell traps:**
  - When pwsh is present, parse the command with
    `[System.Management.Automation.Language.Parser]::ParseInput` first, through `lib/pwsh.py`.
  - Flag `Select-String -Recurse`.
  - Flag automatic variables such as `$Pid` used as names.
  - Flag native `-name:value` arguments.
- **`PIPE_HIDES_EXIT`:** a build, test or compile command piped into head, tail, grep or Select-Object. Warn only.
  A `set -o pipefail;` prefix would add a subcommand that no narrow allow rule matches, so the check never adds
  one.

## Where

`plugins/io-guard/scripts/ioguard/checks/lint.py`, `lib/pwsh.py`, `tests/checks/test_lint.py`.

## Done when

- Replay catches the recorded failures of each class above.
- For each rule, the hits on commands that succeeded are checked on a sample, and the false-refusal rate is under
  0.1%.

## What changed

- **`checks/lint.py`, new, `shell.lint`,** runs after `transport.body` on Bash and PowerShell:
  - `BACKTICK_IN_DOUBLE_QUOTES` refuses an unescaped backtick inside double quotes.
  - `TRAILING_BACKSLASH_QUOTE` rewrites `"C:\dir\"` to `"C:/dir/"` under the rewrite mode, when the command
    ends inside that quote and the rewrite closes it.
  - `INLINE_SCRIPT_INVALID` compiles each Python body Python will read: a quoted heredoc fed to `python` or
    `python -`, an unexpanded `python -c`, and a body moved to a file. A SyntaxError refuses, and a SyntaxWarning
    such as an invalid escape is a warning. A body the Bash tool would halve, or bash would expand, is skipped.
  - `DIALECT_MISMATCH` refuses PowerShell in Bash: an `&` that starts a command, `$env:` and other PowerShell
    variables bash expands, `$_` inside a double-quoted `powershell -Command`, a cmdlet run as a program, and a
    here-string. In PowerShell it refuses `export`, a `<<` heredoc, and `> /dev/null` on Windows, and warns
    on `tail` and `head` on Windows.
  - `POWERSHELL_TRAP`, a code this task adds, refuses `Select-String -Recurse` and an assignment to a read-only
    automatic variable.
  - `PIPE_HIDES_EXIT` warns when a build or test is piped into a filter, with no `pipefail` or `PIPESTATUS`.
    The key `checks.shell.lint.build_commands` names the builds, with generic defaults such as `make`.
- **`lib/shell.py`:** `Scan.backticks`, `Scan.unterminated`, `call_operators`, `trailing_backslash_paths`,
  `forward_slashed`, `piped`, `python_reads_stdin` and `body_files`. `shell.writes` now uses `body_files`,
  which also finds a body in the data folder's `bodies/`, in place of its own pattern.
- **`lib/pwsh.py`:** `blanked`, the command with its strings and comments as spaces.
- **`lib/python_source.py`, new:** `compile_report`, under a lock, because the warnings filters are shared.
- **Tests, 355 in all, up from 321 at `8caeb55`:** `tests/checks/test_lint.py` (22),
  `tests/lib/test_python_source.py` (4), and cases in `test_shell.py` and `test_pwsh.py`.
- **The macOS CI failure** from task 12 is fixed apart, as `8caeb55`. This change only wraps a line of its test.
- **Docs:** `docs/design/architecture.md` sections 1, 2, 3, 4 and 5, `docs/live-checks.md` (the PowerShell errors
  and the `pwsh` start time), `context.md`, `README.md` (the status line, a fixes row, the build command setting),
  `CLAUDE.md` (the layout line), task 13's own table, and task 30 (the projects' build commands).
  `compat.md` needs nothing, because no harness feature is newly relied on. The drawing's Checks box covers it.

Not built, with the reason:

- **`open(` without `encoding=`.** Task 10 gives every Bash call `PYTHONUTF8=1`, so `open()` already reads UTF-8
  there, and the warning would fire on correct code.
- **The parse through `pwsh`.** A `pwsh` start that parses one command takes 191 to 218 ms, against 1 recorded
  parse failure in 3,321 PowerShell calls. `pwsh.commands` and `blanked` read what the rules need.
- **Native `-name:value` arguments, and `&&` on Windows PowerShell 5.1.** No recorded failure of either, and the
  PowerShell tool here runs 7.6.6, which takes `&&`.
- **Python bodies in the PowerShell tool.** 2 recorded failures: a script run through another tool, and a
  double-quoted `-c` PowerShell expands.
- **`PIPE_HIDES_EXIT` in PowerShell.** How the PowerShell tool reports a pipeline's exit code is not probed.
- **`$'...'` inside a `$( )` inside double quotes.** 4 recorded commands failed with unexpected EOF, and 2 of the
  same shape ran, so the cause is not pinned down.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27, over the corpus of 110,379 calls:

- **Refusals of calls that ran:** 11 of 60,622 Bash and PowerShell calls that ran, 0.018%, every one read:
  - 7 Python bodies. 4 results show the SyntaxError. 1 was a broken first try behind `||`. 2 doubled their
    backslashes to survive the halving, so D25's exact move breaks them.
  - 2 backticks. One ran `air` and `fuel` as commands, the other dropped a doubled backtick from a grep pattern.
  - 2 PowerShell in Bash. A `git commit -m @'...'@` whose commit subject starts with `@`, and a bare
    `Get-Content` that failed with its error sent to `/dev/null`.
  - None is a false refusal.
- **Recorded failures caught, per class of this task's table:**
  - trailing-backslash quotes: 15 of 17 rewritten. The other 2 are not this case: a 7.8 KB heredoc the Bash
    tool cut, which `shell.writes` refuses, and a script whose output only prints the error text.
  - The replay found a scanner gap on the way: a command ending right after an opening quote read as closed.
    `Scan.unterminated` is now set wherever a quote runs to the end, with a test.
  - backtick failures: 2 of 2. PowerShell call operators: 5 of 5, and 6 more PowerShell-in-Bash failures.
  - invalid-escape warnings: 66 of 72 are bodies `transport.body` now moves byte-exact, which ends the halving
    that caused them. 3 get its halving warning, 2 get this check's warning, 1 is a script file on disk.
  - `unicodeescape`: 9 of 10 moved the same way, 1 a script file on disk.
- **With the projects' build commands** (task 30): 2,138 Bash calls get `PIPE_HIDES_EXIT`, and 464 of them ran
  with exit code 0 while their output showed an error. The generic defaults hit none of this corpus.
- **Replay:** 85.0 s against 52.6 s without the check, about 0.5 ms per shell call. No check raised.
- `python -m unittest discover -s tests -t .` ran 355 tests, all passing.

Not checked:

- **A live session.** The Done-when needs none, and the refusal's route to the model was checked in task 08.
- **macOS.** CI runs the tests there. The Bash rules are the same, and the PowerShell `/dev/null`, `tail` and
  `head` rules are off on macOS by a test.
