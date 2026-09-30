---
title: Take a program's bare name in one helper
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: one helper names a command's program"
---

## Why

Medium. Ten sites turn a command word into the program's bare name, each its own way, and they disagree on
what comes off.

- `plugins/io-guard/scripts/ioguard/lib/shell.py:326-330`, `SimpleCommand.name`:
  `name = re.split(r"[\\/]", self.words[0])[-1]` then `.exe` off and lower case.
- `plugins/io-guard/scripts/ioguard/lib/shell.py:565`, `matching`:
  `head = re.split(r"[\\/]", words[0])[-1].removesuffix(".exe")`.
- `plugins/io-guard/scripts/ioguard/lib/telemetry.py:128-135`, `program_of`: the first word or the first
  quoted text, `re.split(r"[\\/]", word)[-1]`, nothing off.
- `plugins/io-guard/scripts/ioguard/lib/telemetry_summary.py:135`, `shape`:
  `head = words[0].replace("\\", "/").rsplit("/", 1)[-1]`.
- `plugins/io-guard/scripts/ioguard/lib/rules.py:181-188`, `named`: `PurePath(...).name`, then `.exe`, `.cmd`,
  `.bat` and `.com` off in either case.
- `plugins/io-guard/scripts/ioguard/lib/commit_message.py:31`, `subcommand`:
  `words[0].replace("\\", "/").rsplit("/", 1)[-1].lower() not in ("git", "git.exe")`.
- `plugins/io-guard/scripts/ioguard/checks/shell_writes.py:188`, `in_place`:
  `words[0].rsplit("/", 1)[-1].lower().removesuffix(".exe")`, which leaves a backslash path whole.
- `plugins/io-guard/scripts/ioguard/checks/shell_writes.py:216`, `delegated`:
  `words[0].rsplit("/", 1)[-1].lower()`.
- `plugins/io-guard/scripts/ioguard/checks/shell_writes.py:142`: a whole `SimpleCommand` is built to read its
  `name`: `shell.SimpleCommand(tuple(words), (), (), simple.span).name if words else ""`.
- `plugins/io-guard/scripts/ioguard/checks/lint.py:102`:
  `CMDLET.match(re.split(r"[\\/]", simple.words[0])[-1])`.

So `C:\Git\cmd\git.cmd commit` is git to `rules.named` and not to `commit_message.subcommand`, and a backslash
path is a folder to `SimpleCommand.name` and a program name to `in_place`. Every new reader of a command word
writes an eleventh copy, and the eleventh disagrees with the others somewhere.

## What to build

- One function in `lib/shell.py`, or a module of its own, that gives a word's program name: the last path
  segment on either separator, with the program suffixes off. The caller decides case folding and which
  suffixes count, through arguments with the defaults most callers take.
- Every site above calls it, and the copies go. `shell_writes.py:142` reads the name from the words without
  building a `SimpleCommand`.
- A unit test for the helper at each shape: a bare name, a slash path, a backslash path, `.exe` and `.cmd` in
  either case, and a quoted first word where `program_of` reads one.

## Where

`lib/shell.py`, `lib/telemetry.py`, `lib/telemetry_summary.py`, `lib/rules.py`, `lib/commit_message.py`,
`checks/shell_writes.py`, `checks/lint.py`, and their tests.

## Done when

- A grep of `plugins/io-guard/scripts` for `rsplit("/", 1)[-1]` and `re.split(r"[\\/]"` finds only the helper.
- The suite passes, and a replay over the corpus shows no check's counts changed.

## What changed

Validated on 2026-09-30 before building: all ten sites were there. Task 129 had moved the three in
`checks/shell_writes.py` to `lib/writes.py`, at lines 154, 200 and 228. The grep in "Done when" also matches
`lib/editorconfig.py:136`, which splits a glob's path and names no program, so it stays and the test below
looks for a command word split by hand instead.

`lib/program.py` is new: `program_name(word, suffixes=(".exe",), fold=True)`, the last segment on either
separator, less the first suffix it ends with in any case, and `PROGRAM_SUFFIXES`, moved from `lib/rules.py`.
Each site calls it with the suffixes and the case it had: the shell parser, `matching`, `in_place`,
`delegated` and the interpreter test in `bash_writes` take the default, the rules and the commit reader take
`PROGRAM_SUFFIXES`, and telemetry, the report's `shape` and the cmdlet test keep the case and every suffix.
`bash_writes` no longer builds a `SimpleCommand` to read a name.

Four readers now agree where they disagreed, each shown on HEAD's code before the change:

| Reader | Before | After |
|---|---|---|
| `writes.in_place` on `C:\tools\sed.exe -i` | None | `sed -i` |
| `writes.delegated` on `C:\tools\find.exe ... -exec` | None | `find -exec` |
| `commit_message.subcommand` on `C:\Git\cmd\git.cmd commit` | None | git's commit |
| `rules.named` on `C:/Git/cmd/git.Exe` | `git.Exe` | `git` |

`tests/lib/test_program.py`, 5 tests: each shape of a word, the caller's suffixes and case, a quoted first word
in telemetry, the six readers on one Windows path, and a scan that no module but `lib/program.py` splits a
command word by hand. The scan failed on the 10 sites first, and the readers' test on `in_place`.

Docs: `docs/design/architecture.md` section 1 lists `program.py`. No other doc names these functions.

Evidence, on Windows on 2026-09-30:

- The suite: 1,068 tests, 1,063 before, OK with 2 skipped.
- A replay over the corpus with HEAD's code and with this change: 7 checks, 0 differences.
- Live, Claude Code 2.1.283, from this checkout: `live-refuse` (shell.writes), `live-commit-policy` (the commit
  reader), `live-pipe-once` (shell.lint) and `live-run-wrapped` (the rules on a shell string) pass.
