---
title: Leave PIPE_HIDES_EXIT out when the command already prints the exit code it would hide
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: io-guard trusts an exit code the command printed"
---

## Why

Task 83's report run, 2026-09-29: `PIPE_HIDES_EXIT` warned 4 times in this session. Two were on commands
shaped `python tests/run_all.py > "$TEMP/t.txt" 2>&1; echo "exit $?"; tail -2 "$TEMP/t.txt"; grep ... | head`.
The output's first line was `exit 1`, the real exit code, and the warning still said the exit code 0 was
`head`'s and to read the output for the result. A command that prints `$?` of the run it cares about already
shows it, so the warning repeats with no effect.

## What to build

- `checks/shell_results.py` (or wherever the code is made) leaves the warning out when the command runs
  `echo` or `printf` of `$?` after the command whose failure lines it found, before the last pipe.
- Tests with that shape, and with the shape the warning is for, which still warns.

## Done when

- The shape above gets no `PIPE_HIDES_EXIT`, and `cmd | tail` with a failure in the output still does.

## What changed

- `checks/command_results.py`: `hiding_pipe` returns None when an `echo` or `printf` whose words hold `$?`
  runs after some other command and before the last pipeline. An echo of `$?` as the first command prints an
  earlier code, and one after the pipe makes the last command a single one, where the warning never applied.
  `checks/lint.py`'s warning before the run is unchanged, since before the run nothing was printed yet.
- Docs: `docs/design/architecture.md` (command_results.py). The README states nothing this changed.

Evidence:

- `python tests/run_all.py`: 962 tests, OK, up from 961. New: `...; echo "exit $?"; grep FAIL out.txt | head`
  and `make; printf 'code %s\n' $?; grep error log.txt | sort -u` get no `PIPE_HIDES_EXIT`, and `echo $?;
  python run.py 2>&1 | tail` still does.
- In this session, while writing the test, `PIPE_HIDES_EXIT` fired on `python -m unittest ... | tail -15`,
  which printed no exit code. That is the warning's own case, and it was right.
- Live, Claude Code 2.1.283 on Windows: `live-pipe-once` and `live-results` pass (20260929-134719, -134753).

Checked on Windows 10 on 2026-09-29. Not checked: macOS (task 36).
