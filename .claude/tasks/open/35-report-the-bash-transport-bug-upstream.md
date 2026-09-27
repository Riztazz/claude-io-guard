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
