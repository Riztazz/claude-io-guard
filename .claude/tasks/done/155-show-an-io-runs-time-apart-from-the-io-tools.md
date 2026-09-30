---
title: The io tools' time row holds every io.run's program time, so it reads as a slow io-guard
stage: I
area: cli
created: 2026-09-30
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: the report shows an io.run's time apart from the io tools'"
---

## Why

The lead read SmartTablesHost's "Time taken" table on the settings page on 2026-09-30: "One io tool call" at
p50 67.1 ms, p90 11,209.3, p99 117,801.1, max 180,539.6, over 559 calls. The lead: "it seems the io tools are
regressing in performance".

They are not. 321 of the 559 calls were `io.run`, and an `io.run`'s time is the program it runs. By tool, from
the same telemetry:

| Tool | Calls | p50 | p90 | p99 | Max |
|---|---|---|---|---|---|
| `io.run` | 321 | 863.1 | 27,580.6 | 124,213.1 | 180,539.6 |
| `io.edit` | 137 | 6.4 | 8.8 | 15.2 | 83.7 |
| `io.read` | 71 | 1.1 | 2.6 | 8.1 | 8.1 |
| `io.status` | 19 | 2.9 | 14.5 | 38.5 | 38.5 |

"One tool use, all its hooks" had the same fault, since it summed the `io.run` call into its tool use.

## What changed

`lib/telemetry_summary.py` keeps an `io.run`'s time in `Summary.run_ms`, out of `io_ms` and out of the traces
that `uses` sums. `counts()` carries `run_ms`, and the page's data carries `latency.run`.

- `tools/report.py` prints one more line: `io.run, the program's own time: p50 ...`.
- The settings page's "Time taken" table has one more row: "One io.run, the program's own time".

Over every project for two days, the report now reads:

```
Hook call: p50 17.2 ms, p90 77.1, p99 123.7, max 708.9 (11,700)
io tool call: p50 5.6 ms, p90 8.8, p99 17, max 527.4 (628)
io.run, the program's own time: p50 359 ms, p90 17981, p99 124816, max 329437 (585)
One tool use, all its hooks: p50 80.7 ms, p90 121.1, p99 212.1, max 709.9 (5,380)
```

Before, "io tool call" read p90 6,074.5 and max 329,437, and "One tool use" read p99 18,032.8.

Evidence:

- `test_an_io_run_s_time_is_the_program_s_and_stays_out_of_the_io_tools_time` in `tests/cli/test_report.py`
  failed first, with no `run_ms`.
- `python tests/run_all.py`: 1,139 tests, OK, 2 skipped, against 1,138 at task 154.
- `python tools/report.py --days 2 --html <file>` wrote a page whose data holds `"run": {"n": 585, ...}` and
  whose script names the new row.
- Not seen: the row drawn on the live settings page, which runs the installed plugin.

Not changed: `io.format` also starts programs, and its one slow call, 527.4 ms, stays in the io tools' row.

Docs: `docs/design/architecture.md` names the new line and row in both places that list the times.

Checked on Windows 10 on 2026-09-30.
