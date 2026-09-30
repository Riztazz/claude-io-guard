---
title: Every io call reads "Used plugin io-guard io: ..." in the transcript, with no word on what it does
stage: I
area: mcp
created: 2026-09-30
status: done
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

Seen by the lead on 2026-09-30, in the desktop app on 2.1.283, with the plugin at `34b7823`: the closed row
still reads "Using plugin io-guard io: Run a program without a shell". The description shows only in the
opened row, as `description: LOOK FOR THIS SENTENCE`, first among the input's fields. So the field does not
bring the reason back to the row, and the other options are open again.

Also seen: the `io.run` schema Claude Code gave the session after the restart had no `description`, while the
server declares it first and accepted a call that carried it. Whether the session held an old tool list or
Claude Code drops the field is not known.

The lead then chose the skill, on 2026-09-30: "Let's update the skill then". `skills/io-guard/SKILL.md` has a
new row in its card, "Reach for Read, Edit, Write and Bash first, and an io tool only for the job in its row
below", and "Pick the tool" opens with the same rule and asks for one line of text before a run of io calls.
The page is 147 lines, under its limit of 150. D49 in `context.md` holds the decision.

The skill steers a model and cannot make it comply, so how often a session still reaches for `io.read` is not
measured. `io.run` keeps its `description`, which shows in the opened row.

Docs: `docs/tools.md`, the `io.run` signature in `docs/design/architecture.md`, and D49 in `context.md`.
