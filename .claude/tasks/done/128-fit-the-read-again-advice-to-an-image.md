---
title: Fit the read-again advice to an image or other binary file
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: [STL-1]
platforms: [windows, macos]
commit: "fix: shell.touched's advice for a binary file never names an Edit"
---

## Why

Found in the report of 2026-09-29, a SmartTablesHost session at 16:08 UTC. The agent had viewed
`scratchpad/fab/storyboard/storyboard.png` with the Read tool, then ran a script that drew it again, and got:

```
TOUCHED_BY_SHELL: This command changed C:/Users/felia/AppData/Local/Temp/claude/C--Users-felia-Desktop-projs-unreal-SmartTablesHost/f8b45a5b-d749-4d8e-a53a-cd9b46296c40/scratchpad/fab/storyboard/storyboard.png, read before it. Read C:/Users/felia/AppData/Local/Temp/claude/C--Users-felia-Desktop-projs-unreal-SmartTablesHost/f8b45a5b-d749-4d8e-a53a-cd9b46296c40/scratchpad/fab/storyboard/storyboard.png again before
```

The fact is right: the image the agent saw is old. The step is wrong: no Edit ever applies to a PNG, and the
reason to read it again is to see what the script drew. The message also spells the whole scratchpad path
twice, 330 characters each, where a path from the session's scratchpad could be shown from it.

## What to build

- For a read file whose last profile is binary, the step says to read it again to see the new version, and
  names no Edit.
- A path inside the session's scratchpad is shown from the scratchpad, such as
  `scratchpad/fab/storyboard/storyboard.png`, in this message, if `lib.paths.shown` can take the scratchpad as a
  second root without changing other messages.
- A test for the binary step, and one for the short path.

## Where

`checks/touched.py` (the advice), `lib/paths.py` (`shown`).

## Done when

- The case above reads with a step that fits an image, and `live-touched` still passes.

## What changed

- `checks/touched.py`: a read file whose last profile is binary gets `Read <file> again to see what the
  command made of it.`, and a text one keeps `Read <file> again before the next Edit.`, each step naming only
  its own files. Every path in the message goes through `paths.shown` with the event's scratchpad.
- `lib/paths.py`: `shown` takes an optional scratchpad, and a path under it, and not under the current
  folder, shows as `scratchpad/<rest>`. Callers that pass none are unchanged.
- Test, failing first: a PNG in the scratchpad, read and then redrawn by `python draw.py`, reads `This command
  changed scratchpad/fab/board.png, read before it.` with `Read scratchpad/fab/board.png again to see what the
  command made of it.` (`tests/checks/test_touched.py`). The suite of 1,056 passes on Windows, 2 skipped.
- `live-touched` passed on the CLI 2.1.283.
- Docs: none quote this step or the path form.
- Checked on Windows on 2026-09-29.
