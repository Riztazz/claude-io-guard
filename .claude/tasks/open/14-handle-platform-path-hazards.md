---
title: Handle MSYS path conversion, reserved names and cwd drift
stage: B
area: transport
created: 2026-09-27
status: open
depends-on: [08, 10, 11]
findings: [PTH-2, PTH-4, PTH-5, SHL-8, SHL-9]
platforms: [windows]
commit: "feat: keep slash arguments and device names from breaking Windows commands"
---

## Why

Three Windows traps come from the shell rather than from the agent's text:

- **Path conversion.** Git Bash turns any argument that starts with a slash into a Windows path. 37 results show
  it, most of them Unreal asset paths that arrived as `C:/Program Files/Git/Game/...`.
- **Reserved names.** `2>nul` in Git Bash creates a real file named `nul`, which Windows tools cannot delete.
- **Working directory.** The harness moves the shell back to the project after a `cd`. That happened 5,669 times,
  and each time relative paths in the next call pointed somewhere else.

## What to build

A PreToolUse check on Bash, on Windows only:

- **Slash arguments that are not file paths:** `/Game/`, `/Script/`, `/Engine/`, `/p:`, `/nologo`, `^/trunk`, and
  the prefixes in `checks.win.paths.prefixes`. Prefix the command with `MSYS2_ARG_CONV_EXCL=<those prefixes>`. Use
  `MSYS_NO_PATHCONV=1` only when the command holds no `/c/...` path, because those paths need the conversion. Check
  both variables on Git for Windows before relying on them. A leading assignment stops allow rules matching past
  it, so the prefix is a rewrite under the rewrite mode from task 11 (D12).
- **`2>nul` and `>nul` in Bash:** rewrite to `/dev/null`, under the same rewrite mode. A reserved name in a
  file-tool path (nul, con, aux, prn, com1 to com9, lpt1 to lpt9, with or without an extension) stays a refusal, as
  `RESERVED_NAME` in task 19.
- **cmd quirks:** warn, with the corrected form, on:
  - `start "quoted exe"` without a window title
  - a bare `name.bat` meant to run from the current folder
  - an unquoted `C:\Program Files`
- **TMP or TEMP overridden in a command (SHL-9):** warn.
- **Relative paths after a command that changed directory:** add context naming the current working directory.

## Where

`plugins/io-guard/scripts/ioguard/checks/win_paths.py`, `lib/paths.py`, `tests/checks/test_win_paths.py`.

## Done when

- Live on Windows: a command that passes `/Game/X` to a native program delivers `/Game/X` intact, and
  `python /c/Users/.../x.py` still runs.
- Replay catches the 37 recorded conversions.
- On macOS every rule here is off, by its `platforms` in `CheckMeta`, and a CI test on the macOS runner proves it.
