---
title: Did the ignore check of task 148 slow the Bash hook's tail on 2026-09-30?
stage: I
area: checks
created: 2026-09-30
status: done
depends-on: []
findings: []
platforms: [windows]
commit: "docs: the ignore check is cleared of the Bash hook's slow tail"
---

## Why

PreToolUse Bash, over every project, went from p90 82.8 ms and p99 158.4 on 2026-09-29 to p90 130.6 and p99
380.1 on 2026-09-30. Task 148 landed on 2026-09-30 and added a `git check-ignore` to `shell.writes`, so it was
the first suspect.

## What was measured

No code changed. Both scripts ran from the session scratchpad.

- **How often the check asks.** `shell.writes` alone, over the corpus's 62,100 shell calls, with the call to
  `ignored` counted: 32 calls asked, 0.05%, for 32 distinct paths. It asks only for a new script file, outside
  the scratchpad, inside a repository, that git does not track, and once per path in a session.
- **What one ask costs.** `Git().is_ignored` on five paths in this repository, 20 runs: p50 17.0 ms, max 21.9.
- **Where the tail is.** PreToolUse Bash by project and hour, from telemetry:

| Hour, UTC | Project | Calls | p50 | p90 | Max |
|---|---|---|---|---|---|
| 09-29 12 | claude_io_guard | 276 | 64.9 | 69.9 | 340.6 |
| 09-29 16 | SmartTablesHost | 104 | 90.5 | 109.1 | 220.8 |
| 09-30 02 | claude_io_guard | 127 | 71.5 | 80.1 | 708.9 |
| 09-30 03 | SmartTablesHost | 39 | 127.9 | 151.4 | 216.6 |
| 09-30 06 | claude_io_guard | 50 | 57.8 | 70.5 | 82.3 |
| 09-30 07 | CLICKER | 24 | 102.4 | 143.5 | 380.1 |

## Result

The ignore check is cleared. One Bash call in 2,000 pays 17 ms for it.

The tail is the mix of projects. This repository's Bash hook holds a p50 of 57 to 76 ms on both days. On
2026-09-30 a larger share of the calls came from SmartTablesHost and CLICKER, where the p50 is 90 to 128 ms.
A profile of one plain command here shows where a Bash hook's time goes: two git starts, `rev-parse` for the
root and `status`, 38 ms together. Both repositories are larger than this one, and `git status` costs more in
them. That last step is inferred and was not timed in those repositories.

Not explained: SmartTablesHost's own p50 rose from 90.5 to 127.9 ms between the two hours above, over 39 calls.

Telemetry holds two days, so "by day" is one comparison.

Docs: none changed. `context.md`, "Hooks and MCP", row 44, holds the result.

Checked on Windows 10 on 2026-09-30.
