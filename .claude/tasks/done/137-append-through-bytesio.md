---
title: Append to io-guard's own files through lib.bytesio
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: appends and reads go through bytesio"
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

## What changed

The claims held, with one site moved and one site missing:

- `first_in_file` is in `lib/session.py` now, since task 135 split `lib/context.py`, and not at
  `context.py:393-397`.
- The task named three appends and three reads. A scan of every `lib` module found an eighth site, in
  `lib/proc.py`: a background run's empty log made with `open(log, "wb")`.

What moved:

- `lib/journal.py`: `record` appends `(json.dumps(line) + "\n").encode("utf-8")` through `bytesio.append`, and
  `entries` reads through `bytesio.read_bytes` and decodes UTF-8.
- `lib/session.py`: `first_in_file` reads and appends through `bytesio`, with its lines encoded as UTF-8.
- `lib/telemetry.py`: `Telemetry.record` appends through `bytesio.append`, and `shrink_heads` reads through
  `bytesio.read_bytes`.
- `lib/telemetry_summary.py`: `summarise` reads through `bytesio.read_bytes`.
- `lib/proc.py`: the empty log is written through `bytesio.write_atomic`.

The tests:

- `test_lib_opens_a_file_only_through_bytesio` in `tests/test_layout.py` scans every `lib` module's calls for
  `open`, `read_text`, `write_text`, `write_bytes` and an argument-less `read_bytes`. It failed on the 8 sites
  first, then passed. `bytesio`, `locks` and `logcap` are exempt: `bytesio` is the one opener, `locks` holds a
  lock file's descriptor, and `logcap` runs by its path with the standard library only.
- `test_a_line_is_one_json_object_and_a_newline` in `tests/lib/test_journal.py` pins a journal line's exact
  bytes. It passed before the change and after, which shows the bytes did not move.

Evidence:

- The grep in "Done when" finds `.open("a` and `.open("ab` nowhere in `plugins/io-guard/scripts/ioguard` outside
  `lib/bytesio.py`.
- `python tests/run_all.py`: 1,099 tests, OK, 2 skipped, against 1,097 at task 136.
- `live-empty`, `live-server`, `live-verify`, `live-trust`, `live-stage` and `live-results` passed on the CLI
  2.1.283. The journal and telemetry files those sessions wrote in `workbench/io-guard-home` end in LF, hold no
  CR, and every line parses as JSON.
- `tools/report.py --days 1` shows one `GUARD_ERROR`, `shell.results: OSError 60f78cf32d30` on 2026-09-29 at
  12:16, before this change. Task 98 already covers it.

Docs: `docs/design/architecture.md` lists `bytesio.append` and `bytesio.read_from` in the tree and in the
`bytesio` signatures. No other doc names these sites.

Checked on Windows 10 on 2026-09-30. macOS is covered by CI only.
