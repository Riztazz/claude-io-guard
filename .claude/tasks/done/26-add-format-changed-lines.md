---
title: Format only the changed lines
stage: F
area: mcp
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [15, 23]
findings: [BYT-3, BYT-11, BYT-12]
platforms: [windows, macos]
commit: "feat: run the formatter over changed hunks only, in the file's own endings"
---

## Why

clang-format over a whole file re-indents untouched code and adds namespace closers. CLICKER agents wrote two
scripts to work around it:
- `fmt_hunks.py`, run 128 times
- `unformat.py`, to revert what the formatter changed

A fixed `LineEnding: CRLF` on an LF file left mixed endings (BYT-3).

## What to build

`io.format(paths[], formatter?)`. It works in three steps:
1. Find the changed line ranges with `git diff -U0` through `lib.git`. Take the whole file when it is untracked, or
   the ranges the call gives.
2. Run the formatter over those ranges only, with `clang-format --lines` or the formatter configured for the
   extension.
3. Check the result against the file's profile before writing it, inside `lib.locks.file_lock`.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_format.py`, `tests/mcp/test_tools_format.py`.

## Done when

- A sample of CLICKER files gives the same output as `fmt_hunks.py`. The script is described in
  `baseline/io_traps.html`, and its copy sits in CLICKER's scratchpad if it still exists.
- A file keeps its ending style whatever the formatter config says.

## What changed

- **`io.format(paths, lines = [])`** in `mcp/tools_format.py`. It holds every file, takes the lines
  `git diff -U0 HEAD` names, the whole file when git has no commit of it, or the `lines` the call names for
  one path. It runs the format command on the file's text through stdin, lands the output with
  `lib.edits.carried`, and writes each file once after all of them formatted. A command that cannot start,
  exits nonzero, runs past `io.format.timeout_s` or prints nothing for a file with text is the new code
  `FORMAT_FAILED`, and then no file is written.
- **The `formatter?` argument left the design.** The command comes only from the `format` key in the user's
  own `config.json` (D24), clang-format with `--style=file --fallback-style=none` for C and C++ by default,
  found on `PATH` through `probing.program`. A program the model names would be `io.run` without its rules
  (D14). `--fallback-style=none` keeps a project with no `.clang-format` as it is, where clang-format would
  apply LLVM style.
- **Step 3 became `lib.edits.carried`.** It matches the formatter's output to the file line by line: a line
  the formatter left keeps its own ending, a changed one takes `Profile.new_eol`, and the BOM and encoding
  stay (BYT-3). A run of changes that meets none of the asked lines stays as the file had it, and the result
  names it in `left` (BYT-12, the namespace closers). That goes past `fmt_hunks.py`, which writes the whole
  output, and in the 12 samples no such run came up.
- **`lib/verify.py` became `lib/commands.py`**, shared by `verify` and `format`: `command_for` returns the
  command as written, and `filled` puts in `{file}` and repeats the `{first}`/`{last}` argument per range.
  `verify.command`'s `program` moved to `lib/probing.py`.
- **`mcp/in_place.py`** holds what `io.edit` and `io.format` share: `held`, `load`, `encoded`, `write`,
  `Place`, moved from `tools_edit.py`.
- **`GitPort.changed_ranges` counts from `HEAD`**, staged changes included, with `--text` and `--no-textconv`,
  and answers None for a file git has no commit of. Nothing called it before.
- **`proc.run` takes `stdin`, and a program it starts never reads the caller's own stdin.** It inherited it
  before, and inside the io server that is the client's messages, so a verify command or git run from a hook
  tool could read them.
- Config keys `format` and `io.format.timeout_s` of 30.
- Tests: 658 before, 679 after, all passing, from `python tests/run_all.py`: `test_tools_format.py` 9, one of
  them on the real clang-format when `PATH` has it, `test_edits.py` 6, `test_commands.py` 3, `test_git.py`
  2, `test_proc.py` 1. `requests/legacy.expected.json` lists `io.format`.
- **Evidence.** clang-format 19.1.1 (WinLibs) on stdin: a `.clang-format` with `LineEnding: LF` turned a CRLF
  line outside `--lines` into LF, and a file with no `.clang-format` got LLVM style without
  `--fallback-style=none`. Over 12 CLICKER C++ files, 8 CRLF and 4 LF, each copied into a throwaway repository
  with CLICKER's `.clang-format`, given one new badly formatted line and one line with doubled spaces,
  `io.format` and `fmt_hunks.py --apply` wrote the same bytes in 12 of 12, both pointed at the same
  clang-format. `live-format` passed on the desktop's 2.1.281 and the CLI 2.1.283: `io.edit` put
  `int  y=2;if(y){y++;} return 0;` into a BOM and CRLF `a.cpp` under `LineEnding: LF`, and `io.format` made it
  five formatted lines, left the committed `int  kept=1;` as it was, and kept every CRLF and the BOM.
- **Docs:** `docs/design/architecture.md` sections 1, 2, 4, 5, 7 ("Format the changed lines") and 8, the
  README (status, the io tools, "Your formatter"), `docs/compat.md`, `docs/live-checks.md`, `context.md`, and
  the layout in `CLAUDE.md`. The drawing already names `io.format` in its io tools box.
- **Filed task 39**: a write that adds an invisible character, such as a U+FEFF this task's own test file got
  from a JSON escape, gets a warning by default.
- Checked on Windows on 2026-09-28. Not checked: macOS, which waits in task 36, the Visual Studio clang-format
  `fmt_hunks.py` names, and a format command other than clang-format outside the unit tests.
