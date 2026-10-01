---
title: Small cleanups and modernizations from the shell review
stage: I
area: lib
created: 2026-10-01
status: done
depends-on: [166, 167]
findings: []
platforms: [windows, macos]
commit: "refactor: small cleanups in the shell checks"
---

## Why

Fable's review of 2026-10-01, item 13 and simplifications S5, S11, S14 to S17 and S19. Each is small.

- "pipefail" is a substring test in three places: `echo "pipefail" | grep x` reads as if pipefail were set.
  `checks/lint.py` `hidden_exit` and `checks/command_results.py` `hiding_pipe` also judge "a build piped into a
  filter" two ways.
- The `halved(span)` closure is written twice, in `checks/lint.py` and `checks/transport_body.py`.
- `checks/command_results.py` splits the error text by hand where `str.partition` reads plainer.
- `lib/output.py` makes plurals by hand while `checks/command_results.py` has `plural()`.
- `lib/writes.py` `inside_folder` splits a path with a regex where `PureWindowsPath(...).name` does it.
- `lib/shell.py` slices `text[at:]` for a regex at every redirect, which grows with the square of a long
  command's redirects.
- Modernizations: the scanner's states as an `IntEnum`, `Scanner.pair` as one compiled pattern,
  `itertools.pairwise` in `lib/portable.py`, `match` in `rules.unwrapped` and `writes.in_place`, and
  `slots=True` on the small frozen dataclasses.

## What to build

Each item above, one at a time, with the suite green after each.

## Where

`lib/shell.py`, `lib/output.py`, `lib/writes.py`, `lib/portable.py`, `lib/rules.py`, `checks/lint.py`,
`checks/command_results.py`, `checks/transport_body.py`.

## Done when

- One `piped_into` and one pipefail test on blanked text, both checks calling them, and the rest done or
  each one named here as not worth it.

## What changed

- **`shell.pipefail(command)`** reads the word in the code only, through `blanked`. `exit_candidates`,
  `shell.lint`'s `hidden_exit` and `shell.results`' `hiding_pipe` all call it, so `echo "pipefail" | grep x`
  no longer reads as pipefail being set. `hidden_exit` still also passes a command that reads `PIPESTATUS`,
  quoted or not, since printing it keeps the build's exit code.
- **`Scan.hazard_in(span)`** replaces the two copies of the `halved` closure's search, in `checks/lint.py`
  and `checks/transport_body.py`.
- **`output.plural`** moved from `checks/command_results.py` to `lib/output.py`, and `excerpt` uses it for
  its "lines left out" line.
- **Smaller:** `str.partition` for the error text after its first line, `PureWindowsPath(...).name` in
  `writes.inside_folder`, a compiled `DUPLICATED` pattern matched in place where `split` sliced the rest of
  the command at every redirect, and `itertools.pairwise` in `lib/portable.py`.

Not done, each on purpose:

- **One `piped_into` for both pipe checks.** They answer two questions. `shell.lint` asks, before the call,
  whether any build is piped into another command. `shell.results` asks, after it, whether the last pipe's
  last command gave the exit code. One shared function would have to answer both, so only the pipefail test
  became one.
- **The scanner's states as an `IntEnum`.** The states live in a `bytes` value and are compared as numbers in
  every reader. Names in debug output are the only gain.
- **`Scanner.pair` as one pattern.** It is four plain lines that say what they do, and a pattern adds nothing.
- **`match` in `rules.unwrapped` and `writes.in_place`.** Both branch on value and length together, which
  `if` reads as plainly.
- **`slots=True` on the frozen dataclasses.** A hook builds a few of them per call, so the saving is too small
  to measure.

Evidence:

- The case `echo "pipefail" | grep x` in `tests/lib/test_shell.py`
  `test_the_exit_code_comes_from_the_and_chain_that_ends_the_command`, and
  `test_the_word_pipefail_in_a_string_sets_nothing` in `tests/checks/test_lint.py`, both failed first.
- Full replay, HEAD against this change: no check's decision differs.
- `python tests/run_all.py`: 1,165 tests, OK, 2 skipped, against 1,164.

Docs: `docs/design/architecture.md` lists `shell.pipefail` and `output.plural`.

Checked on Windows 10 on 2026-10-01.
