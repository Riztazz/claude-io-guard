---
title: Read every commit message form git accepts
stage: I
area: checks
created: 2026-09-29
status: open
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
