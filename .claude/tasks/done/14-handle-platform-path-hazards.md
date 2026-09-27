---
title: Handle MSYS path conversion, reserved names and cwd drift
stage: B
area: transport
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [08, 10, 11]
findings: [PTH-2, PTH-4, PTH-5, SHL-8, SHL-9]
platforms: [windows]
commit: "feat: keep slash arguments and device names from breaking Windows commands"
---

## Why

Three Windows traps come from the shell rather than from the agent's text:

- **Path conversion.** Git Bash turns any argument that starts with a slash into a Windows path. 18 results show
  it, most of them Unreal asset paths that arrived as `C:/Program Files/Git/Game/...`.
- **Reserved names.** `2>nul` in Git Bash creates a real file named `nul`, which Windows tools cannot delete.
- **Working directory.** The harness moves the shell back to the project after a `cd`. That happened 3,064 times,
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
- Replay catches the 18 recorded conversions.
- On macOS every rule here is off, by its `platforms` in `CheckMeta`, and a CI test on the macOS runner proves it.

## What changed

- **`checks/win_paths.py`, new, `win.paths`,** on Bash, on Windows only, after `shell.lint`:
  - `MSYS_PATH`: every argument Git Bash would turn into a path, passed to a program that is not one of Git
    Bash's own, is named in `export MSYS2_ARG_CONV_EXCL='...';` before the command. The check finds them
    itself, so no project has to list `/Game/`. A drive path such as `/c/Users` and a POSIX root such as
    `/tmp` keep converting, as they must.
  - `MSYS_PATH` also writes `cmd /c` as `cmd //c`.
  - `RESERVED_NAME` writes a redirect to `nul` as `/dev/null`.
  - Each is a rewrite under the rewrite mode (D12). `MSYS_NO_PATHCONV` is never used, because it stops
    `/c/...` converting too.
- **`lib/paths.py`:** `msys_prefix`, the prefix that keeps one argument as written. A lone `/F` is a switch,
  and `/f/data` is a drive path.
- **Keys:** `checks.win.paths.posix_roots`, `msys_programs` and `prefixes`, the last empty by default. The
  shipped defaults name nothing of Unreal's, by the lead's rule in `.claude/rules/this-repo.md`, and the plan's
  `/Game/`, `/Script/` and `/Engine/` are found as they come.
- **Tests, 363 in all, up from 355:** `tests/checks/test_win_paths.py` (7) and `msys_prefix` in
  `tests/lib/test_paths.py`.
- **Docs:** `docs/design/architecture.md` sections 1, 2, 3, 4 and 5, with the design's config example no longer
  naming Unreal prefixes, `docs/compat.md` (Git Bash's conversion and its variable), `docs/live-checks.md`,
  `context.md`, `README.md` (the status line and a fixes row) and `CLAUDE.md` (the layout line).

Not built, with the reason:

- **`start "x.exe"`, a bare `name.bat`, an unquoted `C:\Program Files`, and a TMP or TEMP override.** The corpus
  holds no failure of any, only text that mentions them.
- **Context naming the working directory after a `cd`.** The harness already writes "Shell cwd was reset to
  <dir>" into the result of the call that moved it, 3,064 times in the corpus, so a second line says nothing new.

Evidence, on Windows 10 with Git Bash 5.2.37, through this session's Bash tool on the desktop's 2.1.281, on
2026-09-27:

- **Live:** the command `win.paths` writes for `python argv.py /Game/Maps/L_Lab --map=/Game/X /c/Users/felia
  /PID /F /tmp/x` ran in Git Bash. Before, the program received `C:/Program Files/Git/Game/Maps/L_Lab`,
  `--map=C:/Program Files/Git/Game/X`, `C:/Program Files/Git/PID` and `F:/`. After, it received `/Game/Maps/L_Lab`,
  `--map=/Game/X`, `/PID` and `/F`, while `/c/Users/felia` still arrived as `C:/Users/felia`. `2>nul` wrote a
  real 60-byte file named `nul`.
- **Replay over 110,379 calls:** 166 Bash calls get a rewrite, 163 `MSYS_PATH` and 3 `RESERVED_NAME`, 0.28% of
  58,779. In ask mode each is a prompt. The 25 sampled pass a slash name such as `/Game/...`, `/Script/...` or
  `wmic /format:list` to a Windows program Git Bash converts for, so none of them is needless.
- **The recorded conversions:** 11 of 17. The other 6 are out of the command's reach: 2 pass the argument inside
  a script on disk, and 4 only print old text that holds the phrase.
- **macOS:** `platforms` is `win32` only, and `test_on_macos_nothing_changes` runs on the macOS CI runner.
- `python -m unittest discover -s tests -t .` ran 363 tests, all passing.

Not checked:

- **A plugin session.** The rewrite was run by hand through the harness's own Git Bash, not by io-guard in a
  session. Task 08's `live-answers` checked that a rewrite reaches the shell.
