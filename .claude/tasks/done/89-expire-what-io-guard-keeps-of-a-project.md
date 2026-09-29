---
title: Expire the tool results, run bodies and command heads io-guard keeps in its folder
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: [72]
findings: [security-review-2026-09-29-8]
platforms: [windows, macos]
commit: "fix: io-guard deletes the project content it keeps after a week"
---

## Why

Fable's security review of 2026-09-29, finding 8, low to medium, checked in the code the same day. io-guard's
folder keeps project content with no expiry: `results/`, where `mcp/toolspec.py` spills whole tool results, file
text included; `runs/<id>/`, `io.run`'s bodies and logs (`mcp/tools_run.py`), which `HandleStore.sweep` drops
from memory only; and `bodies/`, which `checks/transport_body.py` writes. Telemetry keeps 200 characters of every
command for 90 days, and the stats page shows them. A secret typed into a command or read from a file stays there.

## What to build

- The retention the io server runs at its start (task 72) also deletes `results/`, `runs/` and `bodies/` entries
  older than a key, seven days by default, like the snapshots.
- Decide with the lead whether telemetry's `cmd_head` shrinks to its shape after some days.

## Done when

- Old entries of each folder are gone after the server starts, and new ones stay, in tests and live.

## What changed

- `lib/retention.py`: `older(folder, cutoff)` lists a folder's entries whose newest file changed before the
  cutoff, a folder counting by the files under it, and `delete` removes them, logging one it cannot.
- `lib/config.py`: `io.saved_days`, 7, `project_may_set=False`.
- `mcp/server.py`: `expire`, which replaces `expire_telemetry`, deletes the old telemetry as before and the
  old entries of `SAVED`, `results/`, `runs/` and `bodies/`, in the retention thread at the server's start.
  The `bodies` folder in a session's scratchpad is left to Claude Code.
- `cmd_head` is not changed. It needs the lead's call, filed as task 93 with options A, B and C.
- Docs: `README.md` (the fourth user-only key, and the saved content's 7 days), `docs/design/architecture.md`
  (the user-only keys, the retention thread), and D42 in `context.md`.

Evidence:

- `python tests/run_all.py`: 948 tests, OK, up from 947. New: with 7 days, results, a run folder and a body
  past 7 days go, a newer result stays, and a run whose body is 30 days old but whose log changed today
  stays. With 0 every entry stays.
- Live on Windows, Claude Code 2.1.283, 2026-09-29: an entry 10 days old and one 1 day old in each of
  `workbench/io-guard-home/results`, `runs` and `bodies`. After `live-empty` started the io server, the three
  old ones were gone and the three new ones stayed.

Checked on Windows 10 on 2026-09-29. Not checked: macOS (task 36).
