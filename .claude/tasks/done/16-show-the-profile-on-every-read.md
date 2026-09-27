---
title: Show the file's profile on every Read
stage: C
area: bytes
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
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

## What changed

- **`checks/read_profile.py`, new, `read.profile`,** on PostToolUse for Read:
  - It profiles the file's bytes on disk and adds `io-guard: <profile line>`, and one more line with the
    profile's warnings when there are any.
  - It stores the whole file's sha256 in `SessionState.read_hashes`, also after a Read of a few lines.
  - A binary file gets its hash and no line. A missing file, or one past `checks.read.profile.max_bytes`
    (16 MB), gets nothing.
- **`tools/probes/run_probe.py`:** `live-read-profile`, whose verdict reads the transcript's attachment and the
  model's reply.
- **The fallback in Notes is not needed.** Task 03 found that PostToolUse `additionalContext` reaches the model,
  and this task's probe saw it again.
- **Tests, 383 in all, up from 378:** `tests/checks/test_read_profile.py` (5).
- **Docs:** `docs/design/architecture.md` sections 1 and 5, `docs/live-checks.md`, `docs/compat.md` (the new
  probe beside `read-context`), `context.md`, `README.md` (the status line and a fixes row), and `CLAUDE.md`
  (the layout line).

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **Live, the desktop's 2.1.281 and the CLI 2.1.283, Haiku:** after a Read of a BOM and CRLF file indented by a
  tab, the transcript carries the attachment, and the model quoted it word for word: "PostToolUse:Read hook
  additional context: io-guard: CRLF, BOM, UTF-8, tabs, 2 lines".
- **Speed:** the check adds 12.8 ms, best of 20, after a Read of a real 1 MB file, against the 50 ms budget.
- `python -m unittest discover -s tests -t .` ran 383 tests, all passing.

Not checked:

- **macOS.** The live check waits in task 36. CI runs the tests there.
