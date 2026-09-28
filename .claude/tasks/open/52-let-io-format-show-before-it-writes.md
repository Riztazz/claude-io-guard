---
title: Let io.format show what it would change before it writes
stage: I
area: mcp
created: 2026-09-28
status: open
depends-on: [26]
findings: []
platforms: [windows, macos]
commit: "feat: add a dry run to io.format"
---

## Why

io.format writes at once. It formats every line changed since the last commit, and a task that spans several
phases before one commit carries lines an earlier phase left unformatted on purpose. In CLICKER on 2026-09-28,
two one-line lambdas in `Source/CLICKER/Tests/NetSphereBoltMarkTests.cpp` match the rest of that file, and
clang-format would split them. The agent needs to see that before the write, to name `lines` or leave the file
out. `lines` also goes with one path only (`mcp/tools_format.py`, line 93), so a call over nine files cannot
narrow any of them.

## What to build

- A `dry_run` flag: io.format returns each file's diff and writes nothing.
- `lines` per path, as a map from path to lines, so one call can narrow several files.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_format.py`, its tool spec, the skill's tool table, `tests/mcp/`.

## Done when

- io.format with `dry_run` over the CLICKER file above returns the lambda split as a diff, and the file's bytes
  do not change.
