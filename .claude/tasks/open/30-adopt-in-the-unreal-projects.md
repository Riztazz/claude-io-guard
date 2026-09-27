---
title: Adopt io-guard in the four Unreal projects and in this repository
stage: G
area: release
created: 2026-09-27
status: open
depends-on: [11, 12, 17, 18, 20]
findings: [BYT-3, SHW-8]
platforms: [windows]
commit: "each kit ticket carries its own subject"
---

## Why

The four Unreal projects are the first users, and the baseline comes from them. The kit (UNREAL-SHARED) still
installs its own guard hook, `shell-write-guard.py`, into every project, this repository included (task 00).

## What to build

File one kit ticket for each change below, in `UNREAL-SHARED/tasks/open/`:

1. `install.ps1` stops writing the shell-write-guard PreToolUse hook, in both profiles, and that hook leaves each
   project's settings.
2. `tools/CLAUDE.md.template` drops the rules io-guard enforces, and points at the io-guard skill instead.
3. The kit's `.clang-format` sets `LineEnding: DeriveLF` in place of `CRLF`. All 74 kit C++ files are LF (BYT-3).
4. io-guard is installed on the lead's machine and enabled for the four projects and this repository.
5. Each project gets its own `.claude/io-guard.json`, holding:
   - the LFS-heavy trees the guard should skip
   - the verify command for each file extension

   The kit as an extra write root goes in the user's config, because a project file cannot add a root.

## Where

UNREAL-SHARED, the four projects' `.claude/` folders, and the user's io-guard config.

## Done when

- One working session in each project, and one here, runs with io-guard on and without shell-write-guard.
- Task 31 starts measuring from that date.

## Notes

- Kit changes follow the kit's own rules: its tickets, its CLAUDE.md, and the lead's commit grants.
