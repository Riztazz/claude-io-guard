---
title: Enforce the workflow rules that a mechanism can hold
stage: G
area: runtime
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
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

## What changed

- **`commit.policy`** (`checks/commit_policy.py`) refuses a git commit whose message holds a text in
  `commit_policy.forbid`, matched without case, or with `commit_policy.ascii_only` a non-ASCII character, with
  the new code `COMMIT_POLICY`, the text and its line, and the fix. It reads each `-m`, a `-F` file, the heredoc
  a `-F -` reads, a `-m "$(cat <<'EOF' ...)"` body, and a PowerShell here-string, from Bash, PowerShell and
  `io.run`'s argument list. `lib/commit_message.py` finds the message past git's own options, such as `-C` and
  `-c`, and inside short option clusters such as `-am`. Both keys are off by default. `forbid` is the user's
  alone, and a project file may only turn `ascii_only` on.
- **The settings snippet** in the README holds rules 4 and 7: `permissions.ask` for git commit and push in Bash
  and PowerShell, and `permissions.deny` for `git reset --hard`. The release copy of it waits for task 34.
- **The kit ticket** for the prose audit:
  `UNREAL-SHARED/tasks/open/add-python-comments-to-the-comment-audit.md`.
- The probe runner takes a `user_config` for one run, written into the probes' data folder and restored after.
- Tests: 697 before, 708 after, all passing, from `python tests/run_all.py`: `test_commit_policy.py` 6 and
  `test_commit_message.py` 5, with every way a message arrives. The skill page lists `COMMIT_POLICY`.
- **Evidence.** `live-commit-asked` passed on the desktop's 2.1.281 and the CLI 2.1.283: in auto mode, with the
  snippet's rules in the project's settings, the permission prompt tool received the `git commit` before it
  ran, and `git reset --hard HEAD` was refused with no prompt. The snippet sat in project settings, not the
  lead's user settings, which the lead did not ask to change. Both read the same rules. `live-commit-policy`
  passed on both: the co-author commit met `COMMIT_POLICY`, and the next call committed without the line.
  The first run failed because the probe session loaded the lead's `~/.claude/CLAUDE.md` and the model refused
  to commit at all, so the probes' prompts grant the commit in their throwaway repository. Over the corpus's
  339 recorded `git commit` commands, the lead's policy would refuse 74, all for a `Co-Authored-By` line, and
  no other.
- **Found on the way:** Claude Code's `tools/call` carries `_meta` `claudecode/toolUseId` (`context.md`, row
  38), so an io tool call's telemetry can join its hooks' trace. That follows in its own commit.
- **Docs:** `docs/design/architecture.md` sections 1, 2 and 5, the README's status, "Your commit policy" and
  the git snippet, `docs/compat.md`, `docs/live-checks.md`, `context.md` (rows 37 and 38, GIT-8 now task 29),
  and `CLAUDE.md`'s layout. The drawing names no commit check.
- Checked on Windows on 2026-09-28. macOS waits in task 36.
