---
title: Cap a background run's log
stage: I
area: mcp
created: 2026-09-29
status: done
depends-on: []
findings: [RUN-4]
platforms: [windows, macos]
commit: "fix: a background run's log stops at a cap"
---

## Why

The code review of 2026-09-29, slice C item 16, split out of task 105. A background `io.run` keeps running
when its session's io server stops: `lib/proc.py` `Pump.stop` runs only on a timeout or a cancel, and task
105's stop cancels only the calls still waiting for an answer, which a background run is not. Its log in
io-guard's `runs/` folder has no size cap, so a run that prints without end fills the disk until
`io.saved_days` deletes it.

## Already decided

`docs/design/architecture.md`, section 8, says a background run keeps running past the server's end, and its
log stays in io-guard's folder. That stays unless the lead says otherwise. The gap is the log.

## What to build

- A run's log stops growing at `io.run.log_max_bytes`, 64 MB by default, a user setting, and the run's last
  `io.status` says the log was cut.
- A test for the cap.

## Where

`lib/proc.py`, `mcp/tools_run.py`, `mcp/server.py`, `lib/config.py`.

## Done when

- A run past the cap keeps its first 64 MB and says so.

## What changed

- The design choice: the run's output goes through a copier, `lib/logcap.py`, which `proc.background`
  starts as its own process, by its path, with the run's stdout and stderr as its stdin. A copying thread in
  the io server would hold the only read end of the run's pipe, so when the server ended, the run's next write
  would fail and the run would die, against section 8's decision that a background run outlives the server.
  The copier outlives the server as the run does, so the cap holds after it too.
- `lib/logcap.py`: `copy` writes up to the cap, then one `CUT` line, `[io-guard: the log stopped here at its
  size cap, and the run went on]`, then reads and drops the rest, so the run never blocks on a full pipe. It
  answers `--help` with its usage.
- `lib/proc.py`: `background` takes `cap`, creates the empty log itself so a reader never finds it missing,
  and starts the copier before the program. `Pump.watch` waits up to `COPIER_WAIT_S`, 10 s, for the copier
  once the program ends, so `ended` is set only when the log holds the last output.
- `lib/config.py`: `io.run.log_max_bytes`, 64 MB, at least 1, user-only.
- `mcp/tools_run.py`: passes the cap, and `RunOutput.log_cut` is true when the log ends with the `CUT` line,
  which the rendered answer names as `cut at its size cap`.
- Tests, each failing first: `copy` past and under the cap (`tests/lib/test_logcap.py`); a real background
  run of 500 lines under a 1,000-byte cap ends with exit 0, and its log holds 1,000 bytes and the `CUT` line;
  `io.run` with `io.run.log_max_bytes` 1,000 answers `log_cut` (`tests/mcp/test_tools_run.py`).
  `tests/lib/test_proc.py`'s three `background` calls pass a cap. The suite of 1,049 passes on Windows, 2
  skipped.
- `live-run-background` passed on the CLI 2.1.283: the 15-minute run answered `running` through `io.status`,
  then `ended` with exit 0, with its output going through the copier.
- Docs: `docs/design/architecture.md` (the package tree, `background`, how io.run runs, shutdown, the config
  keys), `docs/settings.md` (the runs paragraph), `docs/tools.md` (io.run).
- A run outliving the process that started it, checked by hand on Windows: a starter process called
  `background` with a cap of 2,000 bytes on a program printing 400 lines over about 4 seconds, and exited at
  once, with 77 bytes in the log. The program went on, wrote its `done.txt`, and the log ended at 2,071 bytes,
  the first 2,000 and the `CUT` line.
- Checked on Windows on 2026-09-29.
