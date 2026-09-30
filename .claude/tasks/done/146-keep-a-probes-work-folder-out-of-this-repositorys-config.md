---
title: Keep a probe's work folder out of this repository's config
stage: I
area: infra
created: 2026-09-30
status: done
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

## What changed

The claim held, and the leak was wider than `.claude/io-guard.json`. Two more of this repository's files reach
a work folder under `workbench/`:

- `.editorconfig`, whose `[*] end_of_line = lf` outranks the files around a new file. Task 148's first
  `live-new-folder` run failed on it, and that task shielded its one probe by hand.
- `.gitattributes`, whose `* text=auto eol=lf` applies to a work folder that is no repository of its own.

`tools/probes/run_probe.py`: `prepare_work` writes `shields(probe)` into every work folder before the probe's
own setup, and a file the setup names is never replaced:

- every work folder gets an `.editorconfig` of `root = true`, since an `.editorconfig` walk passes a nested
  repository's root,
- a work folder with `git=False` also gets `.claude/io-guard.json` with `{"schema": 1}`, so `project_root` stops
  there, and a `.gitattributes` of `* !text !eol`, which unsets the two attributes.

A git probe needs neither of the last two: its own `.git` stops `project_root`, and the outer repository's
`.gitattributes` does not reach a nested one. `live-new-folder`'s hand-made shield is gone. No probe tests the
walk up to a parent's config, so none builds a parent.

The tests, in `tests/test_probes.py`: a work folder prepared inside a repository whose three files all say LF,
and turn conform.edit off, is its own project root, and neither file's LF reaches it. It failed first with the
outer repository as the root and LF from both files. A probe's own `.editorconfig` is kept.

Evidence:

- `python tests/run_all.py`: 1,130 tests, OK, 2 skipped, against 1,128 at task 144.
- `live-space-dropped` passed on the CLI 2.1.283 with the lead's `.claude/io-guard.json` as it is, conform.edit
  off in it, where it read FAIL on 2026-09-30 at 04:30. `live-new-folder` passed with no hand-made shield, and
  `live-conform`, `live-verify`, `live-empty`, `live-config` and `live-lines-joined` passed beside them.

Docs: none needed. The probes are described in `tools/probes/run_probe.py` itself.

Checked on Windows 10 on 2026-09-30.
