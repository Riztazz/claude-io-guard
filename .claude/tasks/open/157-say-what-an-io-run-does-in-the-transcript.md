---
title: Every io call reads "Used plugin io-guard io: ..." in the transcript, with no word on what it does
stage: I
area: mcp
created: 2026-09-30
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "feat: io.run takes a description of what it runs"
---

## Why

The lead, on 2026-09-30, with a screenshot of another project's session in the desktop app: "i dont see the
reasoning at all now because every call is 'Used plugin io-guard io: ...'". The group held 25 rows, each the
tool's fixed title: "Read a file byte for byte", "Run a program without a shell", "Edit a file in several
places at once".

The desktop app draws a built-in tool's row itself, "Read foo.py", and a Bash row from the `description` the
model writes for the call. For an MCP tool it draws the tool's `title`, one fixed string per tool. No field of
the protocol carries a label for one call.

The lead chose option 3 of 4: give `io.run` a `description` field, as the Bash tool has, and see what the app
does with it.

## What to build

- `io.run` takes `description`, first in its input, which io-guard reads nowhere.
- The lead looks at a run in the desktop app, and the result goes into `docs/live-checks.md`.

## Done when

- The lead has seen whether the row, or the opened row, shows the description.
- If the row does not show it, the task says so, and the other options are weighed again: the skill sends a
  plain read to the built-in Read, the skill asks for a line of text before a run of io calls, shorter
  titles, and a feature request to Claude Code for a label per call.

## What changed

Built on 2026-09-30, and the look in the app waits for the lead.

`RunInput` in `mcp/tools_run.py` has `description`, first, with the text: "What this run does, in 5 to 10 plain
words, as for the Bash tool. The user reads it in the transcript, and io-guard does nothing with it."

Evidence:

- `test_a_run_takes_a_description_for_the_user_to_read` in `tests/mcp/test_tools_run.py` failed first, with
  "unexpected keyword argument 'description'".
- `python tests/run_all.py`: 1,140 tests, OK, 2 skipped, against 1,139 at task 155.
- Not seen: the desktop app's row for a run that carries a description. It needs the plugin updated and the
  app restarted.

Docs: `docs/tools.md` and the `io.run` signature in `docs/design/architecture.md`.
