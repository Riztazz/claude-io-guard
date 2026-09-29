---
title: Take a program's bare name in one helper
stage: I
area: runtime
created: 2026-09-29
status: open
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
