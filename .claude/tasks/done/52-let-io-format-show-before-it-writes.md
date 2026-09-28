---
title: Let io.format show what it would change before it writes
stage: I
area: mcp
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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

## What changed

- `mcp/tools_format.py`: `dry_run` plans every file as before and writes none. Each `FormattedFile` carries
  `diff`, a unified diff with one line of context, cut at 20,000 characters, and the words say "would change".
  `lines` is now a map from a path, spelled either way `paths` allows, to its ranges, so one call narrows
  several files. A key `paths` does not name is refused. The one-path list is gone, so a caller that sent a
  list now gets `InvalidArguments`.
- `mcp/toolspec.py`: a typed map gets `additionalProperties` in its schema, so the model sees the range shape.
- Tests: `tests/mcp/test_tools_format.py`, a dry run that writes nothing and shows the line both ways, and two
  files with lines of their own. The old one-path tests take the map.
- `tools/probes/run_probe.py`: `live-format-dry`.
- Docs: `docs/design/architecture.md` (the signature, steps 2 and 5), `README.md`, `docs/live-checks.md`,
  `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 832 tests, all passing, up from 830.
- `live-format-dry` passed on 2.1.281 and 2.1.283: the file held the edit exactly as `io.edit` left it, and the
  diff showed `+  int y = 2;`. `live-format` passed again on both, so the write path is as it was.
- Not checked on the CLICKER file itself, which is the lead's. The probe's C++ file has the same shape of change.
- Checked on Windows on 2026-09-28.
