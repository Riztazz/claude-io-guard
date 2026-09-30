---
title: Keep a probe's work folder out of this repository's config
stage: I
area: infra
created: 2026-09-30
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: a probe's session reads only the config the probe gives it"
---

## Why

Medium, for the probes' worth as evidence. A probe runs its session in
`workbench/probes/<id>/<time>/work`, inside this repository. `lib.context.project_root` walks up from the
session's folder to the nearest one holding `.claude/io-guard.json` or `.git`. A work folder with neither, which
is every probe that sets `git=False` and writes no config of its own, gets this repository's root, and so the
lead's own `.claude/io-guard.json`, uncommitted edits and all.

On 2026-09-30, during task 131, `live-space-dropped` read FAIL: the model's Edit went through and the hook
decided nothing. The lead's file sets `checks.conform.edit.enabled` to false, changed on 2026-09-29 at 11:26
from the settings page, so conform.edit never ran. The same Edit through the pipeline offline, with HEAD's code
and with task 131's, is refused with SPACE_DROPPED both times. Run
`workbench/probes/live-space-dropped/20260930-043057` holds the session, and its telemetry shows the
PreToolUse on the Edit with no check and no code. The lead's file also turns commit.policy off, and any probe
of a check the lead turns off later fails the same way.

## What to build

- Each probe's work folder is its own project: `run_probe.py` makes it a git repository, or writes an empty
  `.claude/io-guard.json` with `{"schema": 1}` when the probe gives no config of its own, so `project_root`
  stops there.
- A probe that means to test the walk up to a parent's config, if one exists, says so and builds the parent
  inside its own run folder.

## Done when

- `tests/test_probes.py` shows a probe's work folder is its own project root.
- `live-space-dropped` reads pass with the lead's `.claude/io-guard.json` as it is.
