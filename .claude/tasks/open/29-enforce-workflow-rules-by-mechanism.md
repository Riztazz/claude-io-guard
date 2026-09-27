---
title: Enforce the workflow rules that a mechanism can hold
stage: G
area: runtime
created: 2026-09-27
status: open
depends-on: [08, 12]
findings: []
platforms: [windows, macos]
commit: "feat: settings and a commit check that hold the git rules"
---

## Why

The memory docs say it plainly: CLAUDE.md and rules are context, not enforced configuration, and "to block an
action regardless of what Claude decides, use a PreToolUse hook". Several of the lead's workflow rules can become
mechanisms, the same way io-guard turns writing rules into checks. The kit's rule map, `rules/README.md` in
UNREAL-SHARED, names them by row.

## What to build

All policy lives in configuration, and the mechanism is generic. The lead's rules are one configuration of it.

| Rule, by the kit's rule map row | Mechanism |
|---|---|
| 4, no commit or push without a grant | `permissions.ask` for `Bash(git commit *)`, `Bash(git push *)`, `PowerShell(git commit *)` and `PowerShell(git push *)`. The harness then asks the lead for every commit and every push, auto mode included. A plugin cannot ship permission rules, so the README's settings snippet carries them (task 34) |
| 5, the lead is the only author | A PreToolUse check on `git commit` that refuses a message holding `Co-Authored-By`, `Generated with` or non-ASCII characters, with the fix. It reads the message from `-m`, from `-F <file>`, and from a PowerShell here-string. It is configured per user under `commit_policy`, and off by default for other users of the plugin |
| 7, no `git reset --hard` | `permissions.deny` for `Bash(git reset --hard *)` and `PowerShell(git reset --hard *)`, in the same snippet |
| 32, prose and no bug stories | A prose audit for Python comments and docstrings. It enforces the kit's `prose` skill, so it belongs in the kit beside it: this task files the kit ticket |

## Where

`plugins/io-guard/scripts/ioguard/checks/commit_policy.py`, `tests/checks/test_commit_policy.py`, the settings
snippet in `README.md`, and a ticket in `UNREAL-SHARED/tasks/open/`.

## Done when

- With the snippet in user settings, a commit attempt in auto mode asks the lead, on Windows.
- A commit message carrying a co-author line is refused with the fix, whether it arrives by `-m`, by `-F` or in a
  here-string.
- The kit ticket for the prose audit is filed.
