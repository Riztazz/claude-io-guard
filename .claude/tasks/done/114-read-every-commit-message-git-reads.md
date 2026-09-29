---
title: Read every commit message form git accepts
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: [GIT-8]
platforms: [windows, macos]
commit: "fix: the commit policy reads every message form git accepts"
---

## Why

The code review of 2026-09-29: slice A item 22, slice B item 8.

- git takes a unique abbreviation of a long option. `lib/commit_message.py` `sources` matches only `--message`
  and `--file`, so `--mess "Co-Authored-By: x"`, `--me=...` and `--fil f` give no message, rerun on Windows on
  2026-09-29: `Sources(texts=(), files=())`. Real git accepts `--mess`.
- A `-F` file is read before the command runs. `printf "Co-Authored-By: x" > m.txt && git commit -F m.txt`
  passes, since `m.txt` does not exist yet. `cd sub && git commit -F m.txt` reads `m.txt` from the event's cwd,
  not `sub`.

## What to build

- `sources` takes any unique prefix of `--message` and `--file`, as git does.
- A `-F` file the same command writes first is refused as unread, with a fix that commits in a second
  command. A `-F` path resolves after the command's `cd`, as `shell.writes` does.
- A test per case.

## Where

`lib/commit_message.py`, `checks/commit_policy.py`.

## Done when

- Each case is refused with `COMMIT_POLICY`, or with the unread fix, and `live-commit-policy` still passes.

## What changed

- `lib/commit_message.py`: `sources` takes any start of `--message` or `--file` from `--m` and `--f` on, with
  `=` or with the next word. A start git finds ambiguous, such as `--fi`, is an error in git, so reading it as
  `--file` refuses nothing git would run.
- `checks/commit_policy.py`: a message is a `Message`, its text and its unread files. A Bash `-F` path
  resolves in the folder `shell_writes.located` gives after each `cd`. The command's writes, from
  `bash_writes` or `powershell_writes`, are worked out only when a commit reads a file. A file a
  `cat > file <<'EOF'` writes is read from that heredoc, by the target as written or by its path, where bash
  passes the heredoc as it stands. A file written another way, one not there yet, or one named by a variable
  is unread, and the commit is refused with `COMMIT_POLICY`, `io-guard cannot read the message file m.txt
  before this command runs, since the command writes it or it is not there yet, so the commit did not run.`
  and the fix `Write m.txt in one call, then commit with -F m.txt in the next.`
- `lib/context.py`: `read_or_none` takes a limit, and commit.policy uses it instead of its own copy.
- Found while building: 37 of the 259 recorded commits write their message file with `cat > file <<'EOF'` in
  the same command, then commit with `-F`. Refusing those as unread would cost each a retry, so the heredoc is
  read. Replayed through the check with a forbid list and every existing file present, all 57 recorded Bash
  commits that read a message file got a readable message, and none was refused as unread. Before, the check
  read the file as it was before the command, or nothing, so those 37 were never checked.
- Tests, each failing first: `--mess`, `--me=`, `--fil` and `--fi=` with `--m`
  (`tests/lib/test_commit_message.py`); a `-F` file the command writes with `printf` and one not there yet,
  each refused with the second-command fix; `cd sub && git commit -F m.txt` reading `sub/m.txt`; a
  heredoc-written file read from its heredoc, clean and forbidden (`tests/checks/test_commit_policy.py`). The
  suite of 1,026 passes on Windows, 2 skipped.
- `live-commit-policy` passed on the CLI 2.1.283.
- Docs: `docs/settings.md` (the commit policy paragraph, which also said a project could not set `forbid`,
  wrong since D38).
- Not built: a PowerShell `Set-Location` before the commit. A PowerShell `-F` path resolves in the call's own
  folder.
- Checked on Windows on 2026-09-29.
