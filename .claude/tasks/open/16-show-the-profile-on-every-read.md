---
title: Show the file's profile on every Read
stage: C
area: bytes
created: 2026-09-27
status: open
depends-on: [03, 15]
findings: [BYT-4, BYT-6, ANC-5]
platforms: [windows, macos]
commit: "feat: tell the agent a file's endings, BOM and indent when it reads the file"
---

## Why

Read shows a CRLF file, an LF file and a CRLF file with a BOM identically. That was verified live. So the agent
cannot know which convention it must keep. Agents wrote `endings.py` for this and ran it 107 times.

## What to build

A PostToolUse check on Read:

- **One profile line in `additionalContext`,** for example `io-guard: CRLF, BOM, UTF-8, tabs, 1,284 lines`.
- **One warning line** when the file mixes endings, or holds invalid UTF-8, private-use glyphs or NUL bytes.
- **Store the hash of the bytes the agent saw** in `SessionState.read_hashes`. The freshness checks in tasks 20 and
  21 use it.

## Where

`plugins/io-guard/scripts/ioguard/checks/read_profile.py`, `tests/checks/test_read_profile.py`.

## Done when

- Live on Windows, the model reports the profile line when asked after a Read.
- A 1 MB file adds under 50 ms.

## Notes

- If task 03 finds that `additionalContext` does not reach the model after a Read, fall back to `io.read` (task
  23) and say so in the skill.
