---
title: See a rename the command names as a move, not new files
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: [GIT-2, GIT-7]
platforms: [windows, macos]
commit: "fix: shell.touched sees a named rename as a move"
---

## Why

Found on 2026-09-29, numbering the code review's tasks. A loop of `mv "fable-$s.md" "$n-$s.md"` renamed 12
untracked files, and got:

```
TOUCHED_BY_SHELL: This command created 129-move-shared-mechanism-out-of-checks.md, 130-name-a-program-once.md,
... and 4 more. Delete any new file the task does not need, and keep the rest on purpose.
```

The command names `mv`, so every file it made is one it moved, and the advice to delete new files is wrong.
`checks/touched.py` `moves` pairs a path that left with one that arrived only when both have the same file
name, so a rename, which changes the name, reads as a deletion and a new file. The files were untracked, so
git shows no rename, and the deletion side is `vanished`.

## What to build

- When the command names a move, and as many paths left as arrived, pair them, in the order the command names
  them where it can be read, else by size. A pair is a rename, which needs no advice.
- A test: two untracked files renamed by `mv` in one command name nothing, or `moved a to b`, and never
  `created`.

## Where

`checks/touched.py` (`moves`, `names_a_move`).

## Done when

- The case above gets no delete advice, and `live-touched-move` still passes.

## What changed

The claim held. `moves` in `checks/touched.py` paired a path gone with a path arrived only when `same_file`
found both had one file name, so an untracked `fable-a.md` renamed to `129-a.md` read as `129-a.md` created,
with the advice to delete it.

One part of "What to build" is rewritten: the pairs do not follow the order the command names them. A move the
command names is never shown in the message, since `summary` drops every named move, so a pair's order reaches
only the result's evidence. Size, then the order given, is enough for that, and reading paths out of a loop's
variables, as the recorded `mv "fable-$s.md" "$n-$s.md"` needs, is not possible anyway.

- `moves` pairs by name as before. Then, when the command names a move and as many paths are left gone as
  arrived, `renames` pairs those one to one: each arrival with a gone path of its size, then the rest in the
  order given.
- The module docstring and `moves`' docstring say so.

The tests, in `tests/checks/test_touched.py`:

- `test_untracked_files_the_command_renames_are_no_news` renames two untracked files in the recorded loop's
  shape. It failed first with a `TOUCHED_BY_SHELL` naming both as created, then passed with no result.
- `test_a_named_rename_pairs_each_path_with_the_one_of_its_size` calls `moves` with two files of different
  sizes, given in the other order. It failed first with no pair, then passed with each paired by its size.

Not changed: with more paths arrived than gone, as when a command renames one file and makes another, no path
is paired by rename, and each new one is named as created, as before. Which one is the rename cannot be told
apart there without the command's words.

Evidence:

- `python tests/run_all.py`: 1,107 tests, OK, 2 skipped, against 1,105 at task 140.
- `live-touched-move`, `live-touched` and `live-empty` passed on the CLI 2.1.283.
- `tools/report.py --days 1` shows no code the earlier tasks of the day did not, and one `GUARD_ERROR` from
  2026-09-29, which task 98 covers.
- No replay: the change only drops `TOUCHED_BY_SHELL` warnings for a named move, and the replay runs no command,
  so it has no file system to compare before and after.

Docs: none needed. `docs/design/architecture.md` says `shell.touched` names "nothing for a move the command
names", which now holds for a rename too.

Checked on Windows 10 on 2026-09-30.
