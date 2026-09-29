---
title: Write forward references without quotes
stage: I
area: runtime
created: 2026-09-29
status: open
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
