---
title: Write forward references without quotes
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "style: forward references as bare names"
---

## Why

Low. Python 3.14 evaluates annotations lazily, and the `io-guard-dev` skill says to use the deferred
annotations freely. Twenty-seven annotations still quote a name defined later or in the same class, the idiom
from before 3.14:

- `plugins/io-guard/scripts/ioguard/lib/git.py:95`: `def within(self, seconds: float) -> "Git":`
- `plugins/io-guard/scripts/ioguard/lib/context.py:47`: `def within(self, seconds: float) -> "GitPort": ...`
- `plugins/io-guard/scripts/ioguard/lib/context.py:102,110,182,513,528,541`: `-> "Probe"`, `-> "SessionState"`
  and `-> "Context"`.
- `plugins/io-guard/scripts/ioguard/lib/events.py:39,54,111,146,161`: `-> "Tool"`, `-> "PermissionMode"`,
  `-> "Event"`.
- `plugins/io-guard/scripts/ioguard/lib/anchors.py:121`, `lib/heartbeat.py:25`, `lib/decisions.py:45`,
  `lib/telemetry.py:99`, `lib/results.py:297`, `lib/fakes.py:124`, `checks/pipeline.py:33`,
  `cli/replay.py:51`, `cli/corpus.py:51`.

Each quote is a string a reader parses by eye and a refactoring tool does not rename.

## What to build

- Every quoted annotation becomes the bare name. The one in a `Protocol` body,
  `lib/context.py:47`, is the same.
- Nothing else changes.

## Where

The files above.

## Done when

- `grep -rn '-> "' plugins/io-guard/scripts` finds nothing.
- The suite passes.

## What changed

The count in "Why" did not hold. It said 27 quoted annotations, its own list names 22, and 13 were left:

- Tasks 133, 135 and 136 already wrote 9 of them bare as they moved the code: `lib/heartbeat.py:25` with
  `Era`, the seven in `lib/context.py` when it split into `ports`, `folders`, `session` and `probing`, and
  `checks/pipeline.py:33` with `Budget`'s defaults.
- The 13 left were `cli/corpus.py:51`, `cli/replay.py:53`, `lib/anchors.py:128`, `lib/decisions.py:58`,
  `lib/events.py:45,60,117,152,167`, `lib/fakes.py:124`, `lib/git.py:95`, `lib/results.py:297` and
  `lib/telemetry.py:100`. Each lost its quotes, and nothing else in those files changed.

The test: `AnnotationsNameTheirTypesBare` in `tests/test_meta.py` scans every Python file in `plugins`, `tests`
and `tools` for an annotation holding a string: a return, an argument or a variable. It failed on the 13 sites
first, then passed. Its second test shows the scan finds a quoted return, argument, nested argument and
variable in a built source.

Evidence:

- The Grep tool finds no `-> "` under `plugins/io-guard/scripts`.
- `python tests/run_all.py`: 1,101 tests, OK, 2 skipped, against 1,099 at task 137.
- `live-empty`, `live-server` and `live-results` passed on the CLI 2.1.283. The server imports every module
  these files are in, so a bare name that failed to resolve would have stopped it.

Docs: `docs/design/architecture.md` quoted 9 of the same returns in its signatures, `Event`, `Probe`,
`SessionState`, `Context` and `Decision`, and names them bare now.

Checked on Windows 10 on 2026-09-30. macOS is covered by CI only.
