---
title: Say a hidden exit code once when the errors are already in a short output
stage: I
area: checks
created: 2026-10-01
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: say a hidden exit code once when the output shows the errors"
---

## Why

`python tools/report.py --days 1` on 2026-10-01: `shell.results` warned `PIPE_HIDES_EXIT` 33 times in one day,
30 of them in this repository's own session, and the session acted on none of them.

Nearly every one was a test run filtered for its result on purpose, such as
`python -m unittest tests.lib.test_shell 2>&1 | grep "^FAIL\|^ERROR\|AssertionError\|^OK"`. The output was a few
lines. It held the failures the warning then listed again, because the grep had picked exactly those lines.
The warning told the agent nothing it was not already reading, and it cost a few hundred bytes of context each
time.

`shell.lint`'s `PIPE_HIDES_EXIT`, before the run, already fires once per session (`first_time("pipe-hides-exit")`
in `checks/lint.py`). `shell.results`' copy, after the run, fires on every call whose output has an error line.

The warning still earns its place where the errors are easy to miss: a long output, or one io-guard saved to a
file, where the model reads exit code 0 and a summary and may never reach the error lines.

## What to build

In `checks/command_results.py` `reported`:

- Short output, at most `short_lines` and not saved: give `PIPE_HIDES_EXIT` once per session, by
  `ctx.session.first_time`, the way `shell.lint` does.
- Long or saved output: keep it on every call, as now.

## Where

`plugins/io-guard/scripts/ioguard/checks/command_results.py`, `tests/checks/test_command_results.py`.

## Done when

- A test: a second short, filtered failing run in one session gets no `PIPE_HIDES_EXIT`. A long one still
  does.
- A replay against HEAD shows only the repeats gone.
- `docs/design/architecture.md` says the once-per-session rule where it describes `shell.results`.

## What changed

- `checks/command_results.py` `reported`: a short output, at most `short_lines` and not saved, gets
  `PIPE_HIDES_EXIT` the first time in a session, through `ctx.session.first_time("pipe-hides-errors")`. The
  key is shared by every io-guard process of the session. A long or saved output gets it on every call, as
  before. The `short` test is computed once and serves `ERRORS_IN_OUTPUT` too.
- Task 54 kept the warning after the run on every call because it names what the pipe hid. A long output still
  gets that. A short one already shows the model those lines, so this keeps task 54's reason.
- Tests: `test_a_short_output_says_it_once_per_session_and_a_long_one_every_time` in
  `tests/checks/test_command_results.py`. It failed first, with two warnings where one was wanted.
- Docs: `docs/design/architecture.md`, the `command_results.py` line of the layout. The skill's code table
  still holds, since the code's meaning did not change.

Evidence:

- Replay of the corpus, HEAD against this change, counted per code: `shell.results PIPE_HIDES_EXIT` 557 to 27.
  The other 17 codes are equal. Calls that succeeded with a `shell.results` warning went from 726 to 197, and
  failed calls stayed at 147.
- `python tests/run_all.py`: 1,166 tests, OK, 2 skipped, against 1,165.

Checked on Windows 10 on 2026-10-01.
