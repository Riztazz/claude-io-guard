---
title: win.paths writes cmd //c even when the command turned Git Bash's path conversion off
stage: I
area: checks
created: 2026-10-01
status: done
depends-on: []
findings: []
platforms: [windows]
commit: "fix: win.paths leaves cmd /c alone when conversion is off"
---

## Why

Fable's review of 2026-10-01, item 4. `MSYS_NO_PATHCONV=1 cmd /c "dir"` is rewritten to
`MSYS_NO_PATHCONV=1 cmd //c "dir"`. With conversion off, Git Bash hands `//c` to cmd as written, and cmd prints
its banner and runs nothing. Fable ran each through Git Bash: `cmd //c echo hi` prints hi,
`MSYS_NO_PATHCONV=1 cmd /c echo hi` prints hi, and `MSYS_NO_PATHCONV=1 cmd //c echo hi` and
`MSYS2_ARG_CONV_EXCL='*' cmd //c echo hi` run nothing.

`ALREADY` in `checks/win_paths.py` stops only the prefixes export. The `CMD_SWITCH` edits do not look at it.
The note also says "a lone /c" while `CMD_SWITCH` rewrites `/k` and any `/c` among cmd's words.

## What to build

- No `cmd //c` rewrite when the command sets `MSYS_NO_PATHCONV` or an `MSYS2_ARG_CONV_EXCL` that covers `/c`.
- The note names the switch it rewrote.

## Where

`plugins/io-guard/scripts/ioguard/checks/win_paths.py`, `tests/checks/test_win_paths.py`.

## Done when

- Both shapes with conversion off pass untouched, and `cmd /c echo hi` is still rewritten.

## What changed

`checks/win_paths.py` has `converts(command, switch)`: Git Bash still turns the switch into a path unless the
command sets `MSYS_NO_PATHCONV`, or an `MSYS2_ARG_CONV_EXCL` entry is `*` or a start of the switch, such as `/`
or `/c`. A switch it does not convert stays as written. The note names the switch it doubled, `//k` for `/k`.
`ALREADY` is gone: the two patterns `converts` reads also decide when the prefixes export is skipped.

Evidence:

- `test_cmd_slash_c_stays_when_the_command_turns_conversion_off` and
  `test_the_note_names_the_switch_it_doubled` in `tests/checks/test_win_paths.py` failed first.
- Each of five commands, as win.paths leaves it or rewrites it, printed `hi` through Git Bash 5.2.37's
  `cmd`: `cmd //c echo hi`, `MSYS_NO_PATHCONV=1 cmd /c echo hi`, `MSYS2_ARG_CONV_EXCL='*' cmd /c echo hi`,
  `MSYS2_ARG_CONV_EXCL=/ cmd /c echo hi` and `MSYS2_ARG_CONV_EXCL=/Game cmd //c echo hi`.
- `python tests/run_all.py`: 1,148 tests, OK, 2 skipped, against 1,146.

Docs: none. No code, setting or signature a doc states changed.

Checked on Windows 10 on 2026-10-01.
