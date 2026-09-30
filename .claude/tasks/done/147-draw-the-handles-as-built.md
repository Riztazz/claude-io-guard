---
title: Draw the handles as they are built, with no elicitor
stage: I
area: docs
created: 2026-09-30
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "docs: the drawing shows the handles as built"
---

## Why

Low. Task 140 found this while it fixed the design's package tree. The drawing and the design's list of its
arrows show three things as built that are not:

- `docs/architecture.svg:121`, the `handles` box: its text is "Handles, elicitor" and "runs, snapshots,
  questions", and its `<title>` says the handles are "for background runs and snapshots" and that "The
  elicitor asks the user for a decision, such as a locked file".
  - No elicitor exists. `docs/design/architecture.md`, section 7, "Elicitation in both eras", says "No
    elicitor is built yet, because no tool needs one and no surface shows its form". A user decision goes
    through a PreToolUse hook's `ask` instead.
  - Only `mcp/tools_run.py` imports `mcp/handles.py`, so the one kind of handle is a run. A snapshot's id
    comes from `lib/snapshots.py`.
- `docs/architecture.svg:135`, the `data` box: its `<title>` lists "handles" among the files in io-guard's
  folder. `mcp/handles.py` keeps handles in memory, and a run handle ends with the server.
- `docs/design/architecture.md`, the arrow list at the end:
  - "`io tools` to `Elicitor`: ask the user." and "`Elicitor` to `MCP client`: elicitation/create or
    input_required." name arrows to a box that is not built.
  - "`io-guard folder` to `Config`, `Probe`, `HandleStore`, ..." puts the handle store in the folder.

## What to build

- The `handles` box names run handles only, and its `<title>` says what a run handle is and how long it lasts,
  in the words `mcp/handles.py`'s docstring uses.
- The elicitor leaves the box. The `data` box's `<title>` drops "handles".
- The arrow list loses the two `Elicitor` rows and `HandleStore` from the folder row. Section 7 stays as the
  record of the plan.
- If the drawing's `STEPS` script names either, it changes with the boxes, as `.claude/rules/docs.md` says.

## Where

`docs/architecture.svg`, `docs/design/architecture.md`.

## Done when

- `grep -i elicit docs/architecture.svg` finds nothing, and every handle the drawing names is a run's.
- The drawing parses with `xml.dom.minidom`, is ASCII, and plays each flow when served on localhost, as
  `.claude/rules/docs.md` says.

## What changed

One claim was too strong. The design itself calls a snapshot's id a handle: section 7 says a snapshot handle
"is a folder in io-guard's folder", kept by `lib.snapshots`, not by `mcp/handles.py`'s store. So the fix names
the store's handles as run handles and says where a snapshot's id lives, rather than calling snapshot handles
wrong. The elicitor and the handles in io-guard's folder were wrong as the task said, and one more copy turned
up while checking the drawing: the folder box's visible subtitle also listed "handles".

`docs/architecture.svg`:

- The `handles` box reads "Run handles" over "background io.run runs", and its `<title>` says they are kept in
  memory, each lasting an hour past its program's end, and that a snapshot's id names its folder instead.
- The `data` box's `<title>` and its visible subtitle list "run logs" where they listed "handles", since
  `runs/<id>/output.log` is what io-guard's folder keeps for a run.
- Flow B's step reads "A background run gets a handle, which io.status reads." in place of "A background run or
  a snapshot gets a handle, and a decision goes to the user."

`docs/design/architecture.md`, section 14's lists: `HandleStore` is background run handles, the `Elicitor` box
and its two arrows are gone, and neither the folder row nor the folder arrow names handles. The `Handle`
dataclass's `kind` comment says what `mcp/handles.py` says. Section 7's "Elicitation in both eras" stays as the
record of the plan.

Checked as `.claude/rules/docs.md` asks: the drawing parses with `xml.dom.minidom` and is ASCII. Served through
the `docs` entry at `http://127.0.0.1:8765/architecture.svg`, the box's two lines measure 81 and 118 pixels in
its 190, the page holds no "elicit", the folder box reads "config, probe, snapshots, run logs, locks,
telemetry, heartbeat", and flow B, played, lists the new step.

No test: the change is to a drawing and its description, and no code moved.

Checked on Windows 10 on 2026-09-30.
