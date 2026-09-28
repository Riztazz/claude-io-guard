---
title: Check that the lines an Edit changed hold what new_string asked for
stage: I
area: bytes
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [17, 18]
findings: [ANC-4]
platforms: [windows, macos]
commit: "fix: catch an Edit whose new_string would not land as given"
---

## Why

The Edit tool drops the trailing whitespace of `new_string`, as the kit's `writing-files.md` rule records. In
CLICKER on 2026-09-28 an Edit with `replace_all` turned `.Place.Branch, ` into `.Place.Branch.ToInt(), ` in
`Source/CLICKER/Tests/NetSphereReachTests.cpp`, and five lines came out as `ToInt(),1`. No code named it.
`verify.write` compares only the lines outside the edit (`checks/verify_write.py`, header lines 10 and 11, and
lines 112 to 121), so a difference inside the edited lines is never looked at, although `expected` already
holds the text the call asked for (line 43).

## What to build

- Before the run: when `new_string` ends in spaces or tabs and the file goes on past the match on the same line,
  refuse the Edit. The fix extends `old_string` and `new_string` past the whitespace. Whitespace at a line end
  is safe to lose, so it passes.
- Refuse, never warn. A PreToolUse warning cannot stop the Edit, and the model reads it only after the Edit has
  run, with the damage already on disk.
- First find out whether the hook's `tool_input` still holds the whitespace, or Claude Code strips it before
  the hook sees it. Record the answer in `docs/live-checks.md`.
- After the run: compare the edited lines with `expected` too. Forgive only what the tool restyles, its quotes
  and whitespace at a line end. Report each other difference with the line number and both texts.
- A test for each, from the recorded CLICKER call.

## Where

`plugins/io-guard/scripts/ioguard/checks/conform_edit.py`, `checks/verify_write.py`, `lib/drift.py`,
`tests/checks/`.

## Done when

- The CLICKER Edit above is refused before it runs, and the file keeps its bytes.
- With the refusal off, the same Edit gets a report after it naming the five lines.

## What changed

The probe answered the first question, and the answer reshaped the task. The Edit tool drops nothing. The space
is gone from the model's own call, so the hook's `tool_input` held `new_string` `.Branch.ToInt(),` while
`old_string` kept `.Branch, ` (2.1.283, recorded by a PreToolUse and a PostToolUse hook). That was already live
check 28, found in task 17. So `expected` in `verify.write` lacks the space too, and matches the broken file. The
after-run comparison would never see this, and was not built. The second done-when line goes with it.

- `lib/anchors.py`: `joins(text, old, new, every)` and `Joined`. Each place where old ends in spaces or tabs
  after some text, new is not empty and ends in neither, and the line goes on after the match. Only the one
  match counts without replace_all, since the tool refuses a repeated one.
- `checks/conform_edit.py`: refuses such an Edit with `SPACE_DROPPED`. The message shows each joined line as the
  Edit would leave it. The fix names old_string and new_string one character longer, with the space inside
  both, and asks for one Edit per following character when they differ. `checks.conform.edit.space_dropped`,
  true by default, turns it off.
- It refuses every time. The first version let the same Edit through when sent again, for a model that meant to
  drop the space. Haiku on 2.1.281 sent it again in 1 run of 2, and the words were joined anyway. The longer
  strings carry either intent, so no escape is needed.
- `lib/results.py`: `SPACE_DROPPED`, a refusal in the Bytes layer. `tools/skill.py` wrote its row into the skill.
- `tools/probes/run_probe.py`: `live-space-dropped`, which asks for the CLICKER call and passes when the file
  ends as `ToInt(), 1` and `ToInt(), 2` after the refusal.
- Tests: `tests/lib/test_anchors.py` (4) and `tests/checks/test_conform_edit.py` (4), from the CLICKER call.
- Docs: `docs/design/architecture.md` (the layout line, the codes table, `joins`), `README.md` (the checks
  running, which also named nineteen where task 32 had made twenty-one), `docs/architecture.svg` (the file
  tools' hover text, which parses and is ASCII), `docs/compat.md`, `docs/live-checks.md` (row 28 again, and a
  row for `live-space-dropped`), and `.claude/tasks/context.md` (ANC-4 now points at this task).

Evidence:

- `python tests/run_all.py` ran 819 tests, all passing, up from 811.
- `live-space-dropped` passed 2 runs on 2.1.281 and 2 on 2.1.283 with the refusal as it ships. Each refused the
  replace_all, then two Edits one character longer left the file right.
- The corpus of 2026-09-27 holds 17,370 Edits. 5 have the shape, 4 of them joined text, and all 4 broke the
  file's own spacing: `spawned =[`, `CursorAim(const`, `TakeOnly(TEXT(` and
  `BindViewModelPathToWidgetProperty(UWidgetBlueprint`. None would have been a false refusal. `tools/replay.py`
  cannot measure this rule, since it gives the checks no file contents, so a scratch script ran `joins` over the
  recorded patches instead.
- Checked on Windows on 2026-09-28. The macOS live check waits in task 36.
