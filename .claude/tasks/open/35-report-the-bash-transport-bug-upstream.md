---
title: Add our numbers to the upstream Bash transport bug
stage: I
area: release
created: 2026-09-27
status: open
depends-on: []
findings: [SHW-2, SHW-4]
platforms: [windows]
commit: "none, this is a comment on GitHub"
---

## Why

anthropics/claude-code#92543 has been open since 2026-09-06. It reports two faults in the Bash tool on Windows:
the command is cut at about 8 KB, and every backslash pair is halved. The halving is narrower than the issue
says: a run of backslashes loses half its pairs only when a double quote does not follow it (`context.md`,
"Hooks and MCP", row 25).

The lead's data backs it up, counting each call once:
- 77 of 77 commands between 8 and 16 KB failed, and 10 of 10 over 16 KB.
- The 122 commands the transport failed cost about 262k tokens.
- The error text points at quoting, so agents fix the wrong thing and resend.

## What to build

A comment for the issue. It carries the measured numbers and the live tests from `context.md`, and asks that the
error message name the command length. It holds no project content.

## Where

https://github.com/anthropics/claude-code/issues/92543

## Done when

- The lead has approved the text, and has either posted it or asked for it to be posted. It is a public comment.

## Notes

- It depends on nothing, so it can run at any point.

## Blocked on

The lead's approval of the draft below, and the posting, which is the lead's: it is a public comment.

## Draft, 2026-09-28

We see both faults on Windows 10 with Git Bash 5.2.37, in the desktop app's bundled 2.1.281 and in the CLI
2.1.283. The numbers come from 110,379 recorded tool calls across four projects, each tool use counted once.

**The length cut.** Commands that carry a heredoc, by size, with each apostrophe counted as 4 bytes:

| Size | Failed |
|---|---|
| under 6 KB | 2 of 10,831 |
| 6 to 8 KB | 11 of 158 |
| 8 to 16 KB | 77 of 77 |
| over 16 KB | 10 of 10 |

The largest command that ran was 7,810 bytes, and the smallest that failed was 7,807. Neither an apostrophe nor
the line count is the trigger: a 9.0 KB body with no apostrophe fails the same way, and heredocs of 20 and 70
lines under the limit run. The error is `/usr/bin/bash: -c: line 1: unexpected EOF while looking for matching`
followed by a quote, which points at quoting. So the model fixes its quotes and sends the same length again.
122 commands failed this way, about 1.0 MB, roughly 262k tokens.

**The halving is narrower than the title.** A run of backslashes loses half of them only when a double quote
does not follow it. `echo 'a\\b' | od -c` prints `a \ b`. Four backslashes become two, and three become two,
while a run just before a `"` arrives whole. A quoted heredoc does not protect a body: `python - <<'PY'` with
`print(len(r"\\n"))` prints 2 where 3 was sent. The PowerShell tool and the Write tool keep every backslash.

**What would help.** Name the command's length and the limit in the error, so the model shortens the command or
moves the body into a file instead of requoting it. And pass backslashes through as written.
