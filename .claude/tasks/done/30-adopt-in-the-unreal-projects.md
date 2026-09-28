---
title: Adopt io-guard in the four Unreal projects and in this repository
stage: G
area: release
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [11, 12, 17, 18, 20]
findings: [BYT-3, SHW-8]
platforms: [windows]
commit: "each kit ticket carries its own subject"
---

## Why

The four Unreal projects are the first users, and the baseline comes from them. The kit (UNREAL-SHARED) retired
its own guard hook, `shell-write-guard.py`, on 2026-09-27, so until io-guard runs, no hook checks a shell write
in any project.

## What to build

File one kit ticket for each change below, in `UNREAL-SHARED/tasks/open/`:

1. Done by the kit on 2026-09-27: `install.ps1` writes no shell-write-guard hook, and an install removes it from
   each project's settings.
2. `tools/CLAUDE.md.template` drops the rules io-guard enforces, and points at the io-guard skill instead.
3. The kit's `.clang-format` sets `LineEnding: DeriveLF` in place of `CRLF`. All 74 kit C++ files are LF (BYT-3).
4. io-guard is installed on the lead's machine and enabled for the four projects and this repository.
5. Each project gets its own `.claude/io-guard.json`, holding the LFS-heavy trees the guard should skip, and
   `checks.shell.lint.build_commands` naming its builds, such as `build.bat`, `runuat.bat` and
   `python .claude/tools/shared/build.py`. The list replaces the defaults. Task 13 measured it with those and
   `python .claude/tools/build.py`: 2,138 recorded Bash calls get the pipe warning, and 464 of them ran with exit
   code 0 while their output showed an error.
6. The kit's rule on the Bash tool's backslash halving is corrected and says a body io-guard moves arrives
   byte-exact (D25). Task 11 filed it as `UNREAL-SHARED/tasks/open/correct-the-bash-backslash-halving-rule.md`.

   The lead's own config holds what a project file cannot set: the verify commands and the commit policy
   (D24). The write root it once held left the plan with D27.

## Where

UNREAL-SHARED, the four projects' `.claude/` folders, and the user's io-guard config.

## Done when

- One working session in each project, and one here, runs with io-guard on.
- Task 31 starts measuring from that date.

## Notes

- Kit changes follow the kit's own rules: its tickets, its CLAUDE.md, and the lead's commit grants.

## What changed

- **Installed** on 2026-09-28 at user scope, so every project on the machine gets it: `claude plugin marketplace
  add` this checkout, then `claude plugin install io-guard@claude-io-guard --config python=C:/Python314/python.exe`.
  `~/.claude/settings.json` now lists the marketplace, enables `io-guard@claude-io-guard` and holds the python
  option. The installed copy is this repository at `38df1e4`. A later commit reaches it after `claude plugin
  update io-guard@claude-io-guard`.
- **The lead's `config.json`**, in `~/.claude/plugins/data/io-guard-claude-io-guard/`: `py_compile` as the
  verify command for `.py`, and the commit policy the lead set on 2026-09-27, `Co-Authored-By` and
  `Generated with` forbidden and messages ASCII. `ascii_only` for files stays off, as the lead chose.
- **Each project's `.claude/io-guard.json`**: CLICKER, OrbitalDrift and SmartTablesHost skip `Content/**` and
  `Plugins/*/Content/**`, and the two with Wwise its `ThirdParty/**`. UNREAL-SHARED skips `plugin/*/Content/**`.
  Each names its builds in `checks.shell.lint.build_commands`: the kit's `build.py`, `build.bat`, `runuat.bat`,
  and the common ones the list replaces. This repository's names `python tests/run_all.py` and its tools. The
  four project files sit uncommitted in their own repositories, for the lead to commit there.
- **Kit tickets:** `derive-line-endings-in-the-kit-clang-format.md` (item 3: all 74 kit C++ files are LF,
  checked again) and `point-the-file-rules-at-the-io-guard-skill.md` (item 2, which names
  `rules/generic/writing-files.md` too, since the template holds almost none of those rules). Item 6's ticket
  was already open, and item 1 was done by the kit.
- **Evidence.** io-guard's own loader read each project's config with the lead's, with no error. One `claude -p`
  session in each of the five projects on the CLI 2.1.283, and in CLICKER on the desktop's 2.1.281, found
  `plugin:io-guard:io` connected and wrote its SessionStart, UserPromptSubmit, PreToolUse and PostToolUse lines
  under its own project name. `~/.claude/mcp-needs-auth-cache.json` stayed `{}`.
- This file carries another session's edits from before the task: the kit retired its own guard hook on
  2026-09-27.
- **Task 31 measures from 2026-09-28.**
- **Docs:** `context.md`. The design and the README describe the install already.
- Checked on Windows on 2026-09-28. The Mac waits in task 36.
