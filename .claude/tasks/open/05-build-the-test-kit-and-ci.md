---
title: Build the test kit and CI on Windows and macOS
stage: A
area: infra
created: 2026-09-27
status: open
claimed-by: claude-opus-5-5, session 7eeb509f
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

## Blocked on

**A push, which only the lead can grant.** CI runs on GitHub, and nothing here has been pushed since `a78a1f8`.
The first Done-when line needs the workflow's first run on both runners. Everything else is built and proved on
Windows below. `.claude/rules/this-repo.md` asks for task 34's scrub before a push that makes content public, so
the lead decides whether this push waits for it. Task 07 depends on this task and waits with it.

## What changed so far

- **`tests/`**, standard-library `unittest`. `tests/__init__.py` puts `plugins/io-guard/scripts` on the path, so
  task 07's tests import `ioguard` as the hooks will.
- **`tests/fixtures/`:** the 15 byte fixtures the task names, generated from `tests/support/fixtures.py` by
  `python -m tests.support.fixtures`, and seven hook events Claude Code sent to task 03's probes, scrubbed of
  paths and ids, in `events/`. `MANIFEST.sha256` holds the hash of all 22 files. The NUL-byte fixture is
  `nul-byte.txt`, because Windows turns a file named `nul.txt` into its null device, and the first write of it
  silently wrote nothing (PTH-5).
- **`tests/support/`:** `events.py` builds Bash, PowerShell, Edit, Write and Read events, and the PostToolUse,
  PostToolUseFailure and SessionStart events, with the fields the recorded events carry. `project.py` is
  `TemporaryProject`, a temporary folder of given bytes, committed to git on request. Task 07 adds `Context.fake`.
- **`tests/test_meta.py`:** no test name twice across the suite, every fixture in the manifest with its hash,
  every generated fixture equal to its definition, and git treating every fixture as not text.
  **`tests/test_support.py`:** the builders give the recorded fields, and a temporary project keeps its bytes.
- **`tests/run_all.py`:** the same discovery as `python -m unittest discover -s tests -t .`, failing when no
  test runs.
- **`.github/workflows/ci.yml`:** `windows-latest` and `macos-latest`, on Python 3.14 and `3.x`, with
  `actions/checkout@v7` and `actions/setup-python@v7`. It prints the runner's `core.autocrlf`, runs
  `tests/run_all.py`, installs the `claude` CLI with npm, and when that works validates both manifests without
  `--strict` (task 02).
- **Docs:** `CLAUDE.md` (the layout and the commands), `context.md` (the recorded event fields). The README's
  test command still holds, and the design already describes these checks in section 11.

Evidence, on Windows 10 with Python 3.14.0:

- `python -m unittest discover -s tests -t .` and `python tests/run_all.py` both ran 19 tests, all passing.
- `python tests/run_all.py tests/support` found no tests and exited 1 with "No tests ran from ...".
- A scratch repository holding `tests/`, cloned with `core.autocrlf=true` as the Windows runner does: with the
  real `.gitattributes` all 19 passed. With the `tests/fixtures/** -text` line removed, 3 failed:
  `test_every_fixture_has_the_hash_the_manifest_records`, `test_every_generated_fixture_holds_its_definition`
  and `test_git_treats_every_fixture_as_not_text`.

Not checked: the workflow itself, and macOS. Both need the push above.
