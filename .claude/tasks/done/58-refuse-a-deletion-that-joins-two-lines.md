---
title: Refuse an Edit whose deletion joins two lines
stage: I
area: bytes
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [49]
findings: []
platforms: [windows, macos]
commit: "fix: refuse a deletion that would join the lines around it"
---

## Why

This repository's session `7eeb509f-baa1-4e42-8aec-4f8fd98fdc99` on 2026-09-28 made two Edits of
`tools/probes/run_probe.py` with an empty `new_string` and an `old_string` that opened with a line break, such as
`\n    "live-memory-note": lambda s, n: note_left_alone(n),`. Each one joined the line above the block with the
line below it:

```
SPACE_KEPT = "...ToInt(), 2);\n"DIAGNOSED = ("ANCHOR_NOT_FOUND: ...
"live-space-dropped": lambda s, n: ... in seen(s),    "live-locked": lambda s, n: ...
```

`verify.command` caught the first, since `py_compile` failed. The second still compiled, and nothing named it.
`verify.write` counts the join as the edited line itself, which the tool may restyle, so it gives no
`UNINTENDED_CHANGE`.

Both are what the Edit tool does if it removes the line break after the match whenever `new_string` is empty.
That is a guess until a probe shows it.

## What to build

- A probe: an Edit with an empty `new_string` and an `old_string` of `\nb` on `a\nb\nc\n`. Record the bytes it
  leaves, on 2.1.281 and 2.1.283, in `docs/live-checks.md` and `context.md`.
- If the tool does remove that line break: `conform.edit` refuses an Edit whose `new_string` is empty, whose
  `old_string` opens with a line break and does not end with one, and whose match a line break follows. The fix
  names the `old_string` moved one line break later, which deletes the same lines and joins nothing. A new code,
  or `SPACE_DROPPED` widened with a new name, whichever reads better to the model.
- Tests from the two recorded Edits.

## Where

`plugins/io-guard/scripts/ioguard/lib/anchors.py`, `checks/conform_edit.py`, `lib/results.py`,
`tools/probes/run_probe.py`, `tests/`.

## Done when

- The two recorded Edits are refused, with the `old_string` that deletes the same lines and leaves the lines
  around them apart.

## What changed

The probe confirmed the guess: `edit-delete-join` on 2.1.281 and 2.1.283 left `ac\n` (row 41 of "Hooks and
MCP"). The live runs then showed a second way to the same join: refused, Haiku sent `\nb\n`, which removes both
line breaks itself. So the rule covers every deletion that opens with a line break and ends on one, its own or
the tool's, where both lines around it hold text.

- `lib/anchors.py`: `deletion_joins(text, old, new, every)`, each line such a deletion leaves joined.
- `checks/conform_edit.py`: refuses it with `LINES_JOINED`, the joined lines shown, and the fix naming
  `old_string` one line break later with an empty `new_string`, plus the way to join lines on purpose.
  `checks.conform.edit.lines_joined`, true by default, turns it off.
- `lib/results.py`: `LINES_JOINED`, a refusal in the Bytes layer. `tools/skill.py` wrote its row.
- `tools/probes/run_probe.py`: `edit-delete-join`, the harness fact, and `live-lines-joined`. Also every probe
  now turns off the lead's installed `io-guard@claude-io-guard`. A user setting enables it in every session and
  the CLI loads it from this checkout, so since its install on 2026-09-28 the raw probes ran io-guard, and the
  io-guard probes ran it twice. The debug logs now show it disabled in both.
- Tests: `tests/lib/test_anchors.py` (1) and `tests/checks/test_conform_edit.py` (1), the second from the
  recorded `VERDICTS` Edit.
- Docs: `docs/design/architecture.md`, `docs/live-checks.md`, `docs/compat.md`, `.claude/tasks/context.md`.

Evidence:

- `python tests/run_all.py` ran 843 tests, all passing, up from 841.
- `live-lines-joined` passed 3 runs on 2.1.283 and 2 on 2.1.281 with the rule as it ships.
- The corpus of 2026-09-27 holds 2 Edits of the first shape in 17,370, and neither joined lines.
- Checked on Windows on 2026-09-28.
