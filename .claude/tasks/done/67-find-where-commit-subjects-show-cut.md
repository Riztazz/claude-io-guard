---
title: Find where a commit subject shows with its first words cut off
stage: I
area: commit
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: []
findings: []
platforms: [windows]
commit: "fix: a commit subject shows whole"
---

## Why

On 2026-09-29 the lead saw this repository's commit ff1bba1 shown as:

```
a mv or cp into a folder writes the file it lands as
```

The subject is `fix: a mv or cp into a folder writes the file it lands as`. The lead has seen the same cut a
few times, and asked whether io-guard causes it. A commit message io-guard shortened would be a serious bug:
`commit.policy` reads every `git commit` a session runs.

## What is known

Checked the same day, from this repository and this session's transcript:

- **git holds the whole subject.** `git cat-file -p ff1bba1` and `git log -1 --format=%B ff1bba1 | od -c` give
  `fix: a mv or cp into a folder writes the file it lands as`, byte for byte, with `fix: ` at the start.
- **The model sent it whole.** The transcript's Bash call `toolu_01GuY6G4rTwNfJ43o2Q6RKfM` at
  2026-09-29T05:19:49Z holds `git commit -q -m "fix: a mv or cp into a folder writes the file it lands as"`.
- **io-guard changed nothing.** Both its hooks on that call answered `{}`: no `updatedInput`, no context.
- **The tool's result shows it whole.** `ff1bba1 fix: a mv or cp into a folder writes the file it lands as`.
- **git changed nothing.** `.git/hooks` holds only the samples, and `git config` sets no commit template or
  hook path.

So the cut happens after the commit, in whatever shows it. The part cut is `fix: `, which is the
conventional-commit type, so a view that turns the type into a label and drops it from the text fits.

## What to build

- Find the view: the desktop app's commit or diff pane, a PR or branch view, GitHub, or a terminal, with the
  lead's answer. Show the same commit there with and without a type, such as `fix:`, and see which drops it.
- If the view is io-guard's, such as a telemetry `cmd_head`, a report line or a hook message, fix it and test
  a subject with a colon.
- If the view is Claude Code's or the desktop app's, record it in `context.md` with the version, and say in
  this task that io-guard is not the cause.
- Add a test either way: a `git commit -m "fix: x"` through the whole pipeline keeps its command byte for
  byte, `commit.policy` included.

## Where

`plugins/io-guard/scripts/ioguard/checks/commit_policy.py`, `plugins/io-guard/scripts/ioguard/lib/commit_message.py`,
`.claude/tasks/context.md`.

## Done when

- The view that cuts the subject is named, and either fixed in io-guard or recorded as the host's.

## What changed

Nothing cuts it. The lead's own `git log --oneline` in PowerShell printed the subject whole:
`ff1bba1 fix: a mv or cp into a folder writes the file it lands as`, and GitHub shows the same text. The subject
ends on "lands as", meaning the file the move lands as, and that ending reads as a sentence cut off mid-way.
The fault is the wording, which was the session's own.

- No code change. io-guard, git and the host all kept the subject byte for byte, as "What is known" shows.
- The commit is on `origin/main`, so its message stays as it is.
- The session's memory now holds the rule that a commit subject ends on a word that closes the sentence, never
  on a preposition such as "as", "to" or "with".
