---
title: Guess a legacy code page without a loop in Python
stage: I
area: lib
created: 2026-10-01
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "perf: guess a code page without a loop in Python"
---

## Why

The performance pass of 2026-10-01. Telemetry since 2026-09-29: `PostToolUse` on a Read of a `.png` in CLICKER
took 122.3 ms at p50 and 166.4 ms at p90 over 101 calls. Every other file type took 3 to 4 ms.

`read.profile` profiles every file the agent reads, up to `max_bytes`. On CLICKER's largest PNGs `profile()`
took 466 ms on 8.7 MB, 539 ms on 9.5 MB and 1,220 ms on 21.8 MB. Of the 539, `legacy_guess` took 420: it
built a list of every byte above 0x7F in Python to choose between cp1250 and cp1252, and an image is mostly
such bytes.

## What changed

- `lib/profile.py` `legacy_guess` counts the high bytes and the Central European ones with `bytes.translate`,
  in C. The guess is the same: the loop and the new count agree on 300 random inputs.
- The fix was proposed as a binary-only profile, holding only a binary file's size, BOM and hash. The suite
  refused that. An Edit that adds NUL or control bytes to the first 8 KB of a text file makes it binary, and
  `verify.write` reads the counts of that profile to give `CONTROL_BYTES_ADDED`. Twelve cases of
  `test_each_fault_injected_into_each_fixture_after_an_edit` and `test_a_lost_bom_and_added_bytes_are_counted`
  failed. So every field stays, only the slow count changed, and the subject names that instead.
- Tests: `test_eight_megabytes_of_high_bytes_get_their_code_page_without_a_loop_in_python` in
  `tests/lib/test_profile.py`. It failed first at 0.52 s against a 0.1 s bound.
- Docs: none. The module's own docstring, that every count is a bytes method or a regex, is now true.

Evidence:

- `profile()` on the same PNGs: 128 ms on 8.7 MB, 140 ms on 9.5 MB, 315 ms on 21.8 MB.
- What is left of the 140 ms: the failed UTF-8 decode, `counts_of`'s translates and counts, and `rise_step`.
- `python tests/run_all.py`: 1,167 tests, OK, 2 skipped, against 1,166.

Checked on Windows 10 on 2026-10-01.
