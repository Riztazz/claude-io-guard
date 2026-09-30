---
title: Split lib.context into the modules it holds
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: lib.context split by operation"
---

## Why

Low. `plugins/io-guard/scripts/ioguard/lib/context.py` is 550 lines and holds six kinds of thing, where the
`engineering` skill asks for a module named for its operation, so a helper has a findable home.

- Lines 46-82: the `GitPort`, `FsPort` and `Clock` protocols.
- Lines 85-150: `Probe`, `Snapshot` and `ShellSnapshot`, the values checks keep between hooks.
- Lines 158-273: `SessionState`, with its file-shared warned set through `session_file` and
  `first_in_file` at lines 383-398.
- Lines 276-358: `SystemClock` and `LiveFs`, the live ports.
- Lines 409-444: where io-guard's and Claude Code's folders are, `claude_folder`, `home_folder`,
  `memory_file` and `project_root`.
- Lines 447-491: the config layering, `config_layers`, `trusted`, `config_stamp` and `load_probe`, which
  read `lib.config` and `lib.trust`.
- Lines 494-550: `Context` itself.

A search for "where is Claude Code's folder" lands on `context.py` only because task 122 moved two copies
into it, and `lib/rules.py:33`, `lib/runs.py:11` and `lib/probing.py:13` import `context` for one name each.
Every import of `context` pulls in `config`, `git`, `locks`, `telemetry` and `trust`, so `probing` imports
the whole config loader to type a `ToolVersion`.

## What to build

- `lib/folders.py`: `claude_folder`, `home_folder`, `memory_file`, `project_root`, `session_file`.
- `lib/ports.py`: the three protocols, `LiveFs`, `SystemClock`, `newlines`, `read_or_none`.
- `lib/session.py`: `SessionState`, `first_in_file`, and the two snapshot types it keeps.
- `lib/probe.py`, or `lib/probing.py`: `Probe`, `ToolVersion`, `load_probe`.
- `lib/config.py` takes `config_layers`, `trusted` and `config_stamp`, since they are the layering.
- `lib/context.py` keeps `Context` and imports the rest.
- Every importer names the new module, and `docs/design/architecture.md` section 1 and section 4 list them.

## Where

`lib/context.py` and the modules above, every module that imports from `context`, `tests/lib/test_context.py`,
`docs/design/architecture.md`.

## Done when

- `lib/context.py` is under 120 lines and holds `Context` alone.
- The suite passes, `tests/test_layout.py` included.

## What changed

Validated on 2026-09-30 before building: the six kinds of thing were there, and the file had grown to 588
lines with what tasks 129 and 131 put in it, `tracked`, `project_of`, `file_stamp`, `ToolVersion.this_python`
and the `keys` field.

`test_the_context_module_holds_the_context_alone` in `tests/test_layout.py` came first and failed on 12
classes and 588 lines. It holds that `lib/context.py` declares `Context` alone, in under 120 lines, and that
no module of the package, the tests or the tools imports anything else from it.

Where each piece went:

- `lib/ports.py`, new: `FileStat`, the `GitPort`, `FsPort` and `Clock` protocols, `LiveFs`, `SystemClock`,
  `newlines` and `read_or_none`.
- `lib/folders.py`, new: `claude_folder`, `home_folder`, `session_file`, `memory_file`, `project_root`,
  `project_of` and `repository_root`.
- `lib/session.py`, new: `SessionState`, `Snapshot`, `ShellSnapshot`, `SNAPSHOTS_KEPT`, `ASK_LIFETIME`,
  `first_in_file` and `tracked`.
- `lib/probing.py`: `ToolVersion`, `Probe`, `file_stamp` and `load_probe`, beside the measuring that fills
  them. The task offered `lib/probe.py` or `lib/probing.py`, and one module per job reads better than two
  names a letter apart.
- `lib/config.py`: `config_layers`, `trusted` and `config_stamp`.
- `lib/context.py`: `Context` alone, 81 lines.

The new modules were written with the Write tool, which is the only tool that creates a file, and the moved
code was copied as it stood. The 50 importers were repointed by one script through io.run, which rewrote only
the `from ioguard.lib.context import` statements and wrote each file through `lib.bytesio.write_atomic`.

Docs: `docs/design/architecture.md` section 1 lists the four modules and what moved into `probing` and
`config`, and the two places in the text that named `lib.context.project_root` and `home_folder` name
`lib.folders`.

Evidence, on Windows on 2026-09-30:

- The suite: 1,095 tests, 1,094 before, OK with 2 skipped.
- A replay over the corpus with HEAD's code and with this change: 7 checks, 0 differences.
- Live, Claude Code 2.1.283, from this checkout: `live-empty`, `live-server`, `live-conform`,
  `live-read-profile`, `live-touched`, `live-verify`, `live-trust` and `live-config` pass, 41 seconds for
  the eight.
