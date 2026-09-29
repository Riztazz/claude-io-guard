---
title: Append to io-guard's own files through lib.bytesio
stage: I
area: runtime
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: every append goes through bytesio.append"
---

## Why

Low. `lib.bytesio.append` (`plugins/io-guard/scripts/ioguard/lib/bytesio.py:38-41`) is the one append, and
three older appends still open the file themselves, two of them in text mode. The `io-guard-dev` skill says a
file is bytes, written through `lib.bytesio` and nothing else, and the `engineering` skill says a promotion
deletes the copies in the same change.

- `plugins/io-guard/scripts/ioguard/lib/context.py:393-397`, `first_in_file`:
  `path.read_text(encoding="utf-8")` and `with path.open("a", encoding="utf-8", newline="\n") as out`.
- `plugins/io-guard/scripts/ioguard/lib/journal.py:103-104`, `record`:
  `with path.open("a", encoding="utf-8", newline="\n") as out: out.write(json.dumps(line) + "\n")`.
- `plugins/io-guard/scripts/ioguard/lib/telemetry.py:116-117`, `Telemetry.record`:
  `with path.open("ab") as out: out.write(line)`.

The reads beside them go the same way round `bytesio.read_bytes`, which refuses a device or a pipe:
`lib/journal.py:122` `path.read_text(encoding="utf-8")`, `lib/telemetry.py:149` `path.read_bytes()`, and
`lib/telemetry_summary.py:72` `path.read_bytes()`. These read io-guard's own folder, so the risk is small,
and the cost is one more way to open a file for the next reader to copy.

## What to build

- The three appends call `bytesio.append` with the line already encoded, and the text-mode opens go.
- The three reads call `bytesio.read_bytes`.
- The existing tests of the warned file, the journal and the telemetry still pass, and one test shows a
  journal line's bytes are the same as before the change.

## Where

`lib/context.py`, `lib/journal.py`, `lib/telemetry.py`, `lib/telemetry_summary.py`.

## Done when

- A grep of `plugins/io-guard/scripts/ioguard` for `.open("a` and `.open("ab` finds only `lib/bytesio.py`.
- The suite passes.
