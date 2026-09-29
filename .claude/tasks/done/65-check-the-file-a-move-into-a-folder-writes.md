---
title: Check the file a mv or cp into a folder writes, not the folder
stage: I
area: checks
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [12]
findings: []
platforms: [windows, macos]
commit: "fix: a mv or cp into a folder writes the file it lands as"
---

## Why

On 2026-09-28 this repository's session ran
`mv .claude/tasks/open/64-find-why-the-io-server-exits-on-its-own.md .claude/tasks/done/`, a task file git did
not track yet, into a folder of tracked files. `shell.writes` refused it:

```
SHELL_WRITE: This command writes C:/Users/felia/Desktop/projs/claude_io_guard/.claude/tasks/done, which git
tracks, through mv, so the write skips io-guard's byte checks and Claude Code's checkpoints. Use the Edit tool
to change it, or the Write tool to replace it whole.
```

The file `mv` writes is `.claude/tasks/done/64-find-why-the-io-server-exits-on-its-own.md`, new and untracked.
`bash_writes` in `checks/shell_writes.py` takes the last argument of `cp` or `mv` as the target, and
`tracked` then asks git about the folder, which it answers as tracked. The fix the refusal names cannot move a
file either.

## What to build

- When the last argument of `cp` or `mv` is a folder, by a trailing slash or by being one on disk, the target
  is each source's name inside it. `cp -t folder` and `mv -t folder` name the folder first.
- `tracked` answers for a file. A folder is never a write target.
- A test for each: a move of an untracked file into a tracked folder passes, and a move onto a tracked file
  inside it is still refused.
- Replay: the refusals of `cp` and `mv` before and after, in `## What changed`.

## Where

`plugins/io-guard/scripts/ioguard/checks/shell_writes.py`, `tests/checks/test_shell_writes.py`.

## Done when

- A `mv` of a new file into a folder of tracked files runs with no `SHELL_WRITE`.

## What changed

- `checks/shell_writes.py`:
  - `landed(words, cwd, ctx)` gives the files a `cp` or `mv` writes: the last operand, or each source's last
    name inside the folder. The folder comes from `-t` or `--target-directory`, a trailing slash, or a folder on
    disk.
  - `into_folder` and `inside_folder` do the same for PowerShell's `Copy-Item` and `Move-Item`, with the source
    from `-Path`, `-LiteralPath` or the first operand.
  - `tracked` is unchanged. A folder no longer reaches it as a target.
- `lib/context.py`, `lib/fakes.py`: `FsPort.is_dir`, on `LiveFs` and `FakeFs`. A folder holding only folders
  lists no files, so `list_dir` could not tell it from a file.
- Tests: `tests/checks/test_shell_writes.py` (1, eight moves and copies for both tools). Its `FolderGit` answers
  for a folder as git does, tracked when it holds a tracked file, since `FakeGit` alone let the old code pass.
  Against the HEAD `shell_writes.py` it fails: `mv new.md src/` and `mv new.md src` were refused.
- Docs: `docs/design/architecture.md` (`FsPort`).

Evidence:

- `python tests/run_all.py` from Git Bash ran 870 tests, all passing, up from 869.
- The corpus: 807 recorded `cp` and `mv` commands, 167 of them into a folder, 161 by a trailing slash and 6 to
  a folder still on disk. Those are the calls this changes. The refusals before and after could not be
  counted, since that needs each recorded folder's git state at the time.
- `python tools/ioguard.py check` with this repository's real git:
  `mv .claude/tasks/open/65-... .claude/tasks/done/` passes, and a `mv` onto the tracked `README.md` is refused.
