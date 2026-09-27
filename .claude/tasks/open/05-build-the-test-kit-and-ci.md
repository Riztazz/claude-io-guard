---
title: Build the test kit and CI on Windows and macOS
stage: A
area: infra
created: 2026-09-27
status: open
depends-on: [01, 02]
findings: [BYT-1, BYT-6, BYT-7]
platforms: [windows, macos]
commit: "test: byte fixtures and CI on Windows and macOS"
---

## Why

io-guard promises byte-exact files on two platforms. The tests must run on both, and the fixtures must reach the
tests with their bytes intact, or every byte test passes on the wrong input. While the lead's Mac is down, the
macOS runner is the only macOS evidence there is (D21).

## What to build

- **`tests/`**, standard-library `unittest`, mirroring the package. `python -m unittest discover -s tests -t .` runs
  everything.
- **`tests/fixtures/`**, one file per case: CRLF, LF, mixed endings, a lone CR, BOM with CRLF, BOM with LF,
  cp1250 bytes (invalid UTF-8), a private-use glyph, a NUL byte, tab indent, space indent, both, no final
  newline, an empty file, and a 300 KB file. Task 01 marks them `-text`.
- **A fixture self-check.** `tests/fixtures/MANIFEST.sha256` holds each fixture's hash, and a test compares. It
  fails when git converted a fixture.
- **`tests/support/`:** builders for a hook event on Bash, PowerShell, Edit, Write and Read, and a temporary project
  root. Task 07 adds `Context.fake`.
- **`tests/test_meta.py`:** fails on a duplicate test method name. Task 07 extends it to codes and checks.
- **`.github/workflows/ci.yml`:** a matrix of `windows-latest` and `macos-latest`, on Python 3.14 and the newest
  release (D15). It runs the unit tests, and fails when a run reports zero tests. `claude plugin validate` runs there
  too if the CLI installs on the runner.

## Where

`tests/`, `tests/fixtures/`, `tests/support/`, `.github/workflows/ci.yml`.

## Done when

- CI is green on both platforms.
- Committing a fixture without `-text` makes the self-check fail on the next CI run.
- A run with no tests found fails CI.
