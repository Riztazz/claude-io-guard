---
title: Keep the io server up on bad input, and stop it on time
stage: I
area: mcp
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: the io server survives bad input and stops on time"
---

## Why

The code review of 2026-09-29, slice C items 8, 9, 10 and 16.

- **A bad `probe.json` kills the server at its start, in every session.** `lib/context.py` `load_probe` has no
  error handling, and `Probe.from_json` reads `raw["os"]` and `raw["fs_case_insensitive"]`. A file of
  `{"os": "win32"}` gave `KeyError: 'fs_case_insensitive'` and exit 1 before the first request. The session
  probe that would rewrite the file runs through the same dead server, so only deleting it helps.
- **A malformed request ends the read loop.** In `mcp/server.py` `take`, a `tools/call` with a list `id`
  raises `TypeError` from the token table, a cancel with a list `requestId` the same, and a string `params`
  an `AttributeError`. The docstring's "the loop goes on" holds only for a line that is not JSON.
- **The stop waits for every running call, however long.** `stop()` waits `DRAIN_S`, 2 s, then
  `shutdown(wait=False)`, but the interpreter joins the pool's threads at exit. With an `io.run` sleeping 12 s
  and stdin closed at 1.5 s, the server exited 10.8 s later. No cancel token is set at the stop.
- **Background runs outlive the server**, and their logs have no size cap. `proc.Pump.stop` runs only on a
  timeout or a cancel.

## What to build

- `load_probe` treats a file it cannot read as no probe, logs it, and the session probe writes a new one.
- `take` answers `INVALID_REQUEST` for an `id`, a `requestId` or `params` of the wrong type, and the loop goes
  on. A test per case.
- `stop()` sets every running call's cancel token, waits `DRAIN_S`, and the worker threads are daemon threads
  or are left unjoined, so the process exits within `DRAIN_S` plus a second.
- A decision for the lead: a background run stops with its server, or keeps running to its own end. Either
  way, its log stops growing at a cap, `io.run.log_max_bytes`, 64 MB by default.

## Where

`lib/context.py` (`load_probe`), `mcp/server.py`, `mcp/tools_run.py`, `lib/proc.py`.

## Done when

- The broken probe file, the three malformed requests and the 12 s run each behave as above, in a test that
  starts the real server.

## What changed

- `lib/context.py`: `load_probe` reads a `probe.json` it cannot parse, or one missing a key, as no probe, with
  a warning line, so the server starts and the next session probe writes the file again.
- `mcp/server.py`: `take` answers a request whose `id` is not a string, a number or null, or whose `params` is
  not an object, with `INVALID_REQUEST`, and a cancel whose `requestId` is not a string or a number is
  ignored, so the loop goes on. `stop` waits `DRAIN_S` (2 s) for the running calls, cancels what still runs,
  and gives it `CANCEL_S` (1 s) more. Cancelling first, before the drain, broke the recorded request scripts,
  which close stdin right after their last request, so the calls get their drain first.
- Tests, each failing first: three broken probe files (`tests/lib/test_context.py`), a list id, a list
  `requestId` and text params, then a request that still gets its answer, and a call still running at the
  stop that ends within 4 s (`tests/mcp/test_server.py`). The suite is 999, all passing, 2 skipped, on
  Windows.
- The real server, with an `io.run` of a 12 s sleep and stdin closed at 1.5 s, exited 2.2 s later and
  answered the run `CANCELLED`. The review measured 10.8 s before. `live-server` passed on the CLI 2.1.283.
- The fourth part, background runs, split out as task 124: the design already keeps a background run past
  its server's end (section 8), so what is left is a cap on its log.
- Docs: `docs/design/architecture.md` (the shutdown list), the `server.py` docstring.
- Checked on Windows on 2026-09-29.
