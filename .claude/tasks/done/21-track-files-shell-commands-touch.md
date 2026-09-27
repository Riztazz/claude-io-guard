---
title: Tell the agent which files a shell command changed
stage: D
area: stale
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-27
depends-on: [03, 10, 16]
findings: [STL-1, BYT-2, GIT-2]
platforms: [windows, macos]
commit: "feat: mark files a shell command changed as needing a fresh read"
---

## Why

A formatter, a script or git can change a file behind the agent's back:
- At best, the next Edit fails with "modified since read".
- At worst, a script has rewritten every line ending without anyone noticing (BYT-2).

The agent needs to hear which files a command changed.

## What to build

- **Before the command** (PreToolUse on Bash and PowerShell). Take a cheap snapshot, which is the primary source:
  - `git status --porcelain`, from the watchdog's cache when the server runs it
  - the modification times of the tracked files the agent has read this session (the read set from task 16)
- **After the command** (PostToolUse). Compare against the snapshot:
  - **Changed files the agent has read** get `TOUCHED_BY_SHELL` context: "re-read before editing: X, Y".
  - **New untracked files** are listed (GIT-2).
  - **Every changed file** is compared against its last profile with task 18's code, so a script that rewrote the
    endings is caught.
- **`bashEditDiff` is a secondary source.** Task 03 confirmed it arrives inside `tool_response` only with
  `bashEditDiffEnabled: true` in user settings, as `{"files": [{"filePath", "hunks": [...]}]}` (`context.md`,
  "Hooks and MCP", row 6), so the README's settings snippet carries that line (task 34).
- **An Edit after a shell change no longer fails.** Task 03 saw it apply with a note that the file was modified
  since it was read (row 5), so this notice is the only warning the agent gets before it edits over the change.
- **Stay under 200 ms on the Unreal repositories.** Skip the untracked-file scan of `Content/` and other LFS-heavy
  trees, as set in `skip_trees`.

## Where

`plugins/io-guard/scripts/ioguard/checks/touched.py`, `tests/checks/test_touched.py`.

## Done when

- Live on Windows: `clang-format -i` on a file the agent has read produces the re-read notice.
- Live on Windows: a script that converts a file's endings is reported.
- Latency is measured on CLICKER and stays under the 200 ms budget.

## What changed

Checked on Windows 10 on 2026-09-27, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **`checks/touched.py`, `shell.touched`.** Before a Bash or PowerShell command it keeps a `ShellSnapshot`: git
  status for the session's repository, and the size and time of each file in the read set. After the command,
  one `TOUCHED_BY_SHELL` names the read files whose size or time moved, with the step to read them again, and
  the tracked files git status newly shows as changed, created or deleted. `verify.write`'s `compare` then names
  what the command did to each read file's endings, BOM, encoding or indent, against the profile the agent last
  had. A `bashEditDiff` in the response adds its files. `skip_trees` globs leave changes out.
- **The read set is profiles now.** `SessionState.read_hashes` became `read_profiles`, whose profile holds the
  hash. `read.profile` keeps the whole profile, and `verify.write` keeps it current after the agent's own write,
  so a later command is blamed only for what it did. The snapshot store takes a `ShellSnapshot` beside a file
  `Snapshot`.
- **Helpers with a second caller moved.** `context.repository_root` replaces `location.py`'s own, and
  `paths.shown` replaces `diagnose.py`'s. `EOL_MISMATCH` from `compare` now says to write the file back in its
  own endings unless the task asked for the new ones. `skip_trees` is a global key, empty by default.
- **Not built:** GIT-7, git status listing files that did not change, which this report does not read, left the
  findings. Tracked files the agent never read are named, but their bytes are not compared, because that needs
  HEAD's blob of each one.

Evidence:
- `python tests/run_all.py` ran 509 tests, all passing, against 501 after task 20.
- `run_probe.py verdicts`: `live-touched` passes on 2.1.281 and 2.1.283. After `clang-format -i a.cpp` the model
  saw `TOUCHED_BY_SHELL: This command changed a.cpp, read before it. Read a.cpp again before the next Edit.`
  After a script turned `conv.txt` from CRLF into LF, it also saw `EOL_MISMATCH: This command changed conv.txt
  from CRLF to LF line endings. Unless the task asked for LF, write conv.txt back with CRLF line endings.`
- Latency, the Done-when, with 20 read files over 10 commands: 128 ms per command on CLICKER at p50, 71 ms before
  and 57 ms after, under the 200 ms budget. OrbitalDrift 143 ms, SmartTablesHost 92 ms. `git status` alone takes
  37 to 64 ms on these repositories, and excluding `Content` through a pathspec made it slower, so `skip_trees`
  filters the report rather than the scan.

Docs updated: `architecture.md` sections 1, 2, 4 and 5. `context.md`: a task 21 paragraph. `live-checks.md` and
`compat.md`. The README's status line, a row in "What it fixes", and a `skip_trees` setting. `CLAUDE.md`'s
layout. The drawing still holds: its Checks box already names the stale view, and no call flows differently.

Not checked:
- macOS, live or in CI until the lead pushes.
- A command that takes past the pipeline's 300 ms before `shell.touched` runs skips it, and then no report
  comes for that command. No probe measured how often that happens.
