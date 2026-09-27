---
name: io-guard-dev
description: How io-guard's own code is laid out, written, tested and verified. Read before writing or reviewing code in this repository, adding a check or an MCP tool, writing a test, running replay, or reporting a result. Covers the package layout and its import rules, the Python rules the plugin keeps, the six test levels, replay, live checks on Windows, and where to read telemetry. The design itself is docs/design/architecture.md.
---

# Working on io-guard

The design is `docs/design/architecture.md`, and every signature there is a contract. The decisions behind it are
D1 to D24 in `.claude/tasks/context.md`. This page is how the code gets written and proved. The kit's generic
skills hold the rules for every project: `engineering` (with `references/python.md`), `testing`, `verification`
and `prose`.

## The card

| Rule | Why | Section |
|---|---|---|
| **Shipped code is standard library Python 3.14** | Claude Code installs no Python packages for a plugin (D4, D15) | Python here |
| **`lib` is mechanism. `checks` is policy on `lib`. `hooks`, `mcp` and `cli` are the ways in, on both, and never import each other** | A test that has to build a `Context` to reach a `lib` function has found a leak | Layout |
| **A file is bytes, written only by `lib.bytesio.write_atomic`, and an io tool holds `lib.locks.file_lock` around it** | `open(path, "w")` truncates first (BYT-9), and two sessions' servers can edit one file (D13) | Python here |
| **A hook's stdout is its protocol** | One stray print corrupts the answer | Python here |
| **Every policy value is a config key with its default in code** | The lead: "configurable as everything else should be" (D16) | Layout |
| **Every code in `CODES` has a test that produces it** | The tests are generated from the table, so a code without one fails the suite | Tests |
| **A rule ships after replay, with its false refusals under 0.1%** | A refusal of a harmless command teaches agents to route around the guard | Replay |
| **Harness behaviour is checked live on Windows, with the Claude Code version recorded** | Only a session shows what the harness does, and the lead's Mac is down (D21) | Live checks |

## Layout

`architecture.md`, section 1, has the tree. Three rules hold it together:

1. **`lib` imports only the standard library and other `lib` modules.** It holds no config, no session and no
   decision.
2. **`checks` imports `lib`. `hooks`, `mcp` and `cli` import `lib` and `checks`, and never each other.** The one
   exception: `mcp.tools_hook` calls `hooks.bridge`. `tests/test_layout.py` enforces all of it.
3. **`tools/` scripts import `ioguard.cli` and hold no logic.** A copy of the logic in a script tests a parallel
   implementation.

**A check is one class with one `run`** (`architecture.md`, section 3). It is registered by name in
`default_registry()`, declares its codes, its config keys and its cost in `CheckMeta`, and returns a `Decision`
for everything expected. It raises only on a bug, and the pipeline fails open around it (D7).

## Python here

`engineering`, `references/python.md`, holds the general Python rules. These are the ones this repository adds or
tightens.

- **Standard library only in `plugins/io-guard/`.** Tests and tools prefer it too, and a dev dependency needs the
  lead's approval.
- **Python 3.14 is the floor.** Use `match`, `X | None` and the deferred annotations freely, and write no
  `from __future__ import annotations`.
- **Files are bytes.** Read with `lib.bytesio.read_bytes`, decode UTF-8 explicitly, and treat a decode error as a
  fact about the file. Write through `lib.bytesio.write_atomic` and nothing else.
- **A hook reads one event from `sys.stdin.buffer`, writes one ASCII JSON answer to `sys.stdout.buffer`, and exits
  0.** Diagnostics go to the debug log. An exception goes to the fail-open boundary.
- **A subprocess is `lib.proc.run` with an argument list and a timeout.** Never `shell=True`. Git runs as
  `git -c core.quotepath=false` with `-z` wherever paths are parsed.
- **A check reads `ctx.platform` and `ctx.probe`, never `sys.platform`.** Every platform difference lives behind a
  `lib` function that takes the `Platform`.
- **Lines stop at 110 characters**, code and comments alike (D17).
- **A module is named for its operation**, a value that crosses modules is a frozen dataclass, and every public
  function has type hints.

## Tests

`architecture.md`, section 11, names the six levels: unit, check, pipeline, hook, conformance and replay, plus the
live checks.

- **`python -m unittest discover -s tests -t .` runs everything.** CI fails when a run reports zero tests.
- **`tests/` mirrors the package.** `tests/lib/test_profile.py` tests `ioguard/lib/profile.py`, and shared helpers
  live in `tests/support/`: event builders, `Context.fake`, a fake git and a temporary project root.
- **Fixtures are bytes.** `tests/fixtures/` is `-text` in `.gitattributes`, and `MANIFEST.sha256` holds each
  fixture's hash for the self-check test.
- **`tests/test_meta.py` keeps the suite honest:** no duplicate test names, a test for every code and every check,
  loose output schemas, and fixture hashes that match.
- **Rewrites are tested for the fixed point.** Running the pipeline on its own output gives no rewrite and the same
  verdict.
- **CI runs Windows and macOS on GitHub's runners, on 3.14 and the newest release.** The runners stand in for the
  lead's Mac while it is down.

## Replay

- **`tools/replay.py` runs every check over `corpus/`** without executing anything, and reports per check what it
  would fix, refuse and warn, split by whether the recorded call succeeded.
- **Before a rule ships, read every refusal of a call that succeeded.** The false-refusal rate stays under 0.1% per
  rule, and the numbers go into the task's `## What changed`.
- **`corpus/` never leaves the machine** (D8).

## Live checks

- **Check in the desktop app's Code tab first, then the CLI.** Record the Claude Code version with every result.
- **Windows only until the Mac is back** (D21). A task's macOS live check moves to task 36, and the task says so in
  its `## What changed`.
- **Reload after every change:** `/reload-plugins`, or a new session. A change that seems to do nothing may not be
  loaded yet.
- **Record each confirmed harness fact** in `docs/live-checks.md` and `docs/compat.md` (task 04), and in
  `context.md`.
- **Run io-guard live from this checkout with a `live-*` probe** in `tools/probes/run_probe.py`. It starts
  `claude -p --plugin-dir plugins/io-guard` with the `python` option set, puts `tests/support/inject` on
  `PYTHONPATH`, and names the test checks from `tests/support/injected.py` in `IOGUARD_TEST_CHECKS`. The plugin
  runs as shipped, and the run keeps the session's telemetry. A new check adds its own `live-*` probe.
- **A verdict reads the transcript, never the model's summary.** The model leaves lines out when it quotes. A
  hook's context is a `hook_additional_context` attachment in `~/.claude/projects/<cwd>/<session>.jsonl`.

## Where to look

| Question | Where |
|---|---|
| What would the checks do to this command? | `python tools/ioguard.py check "<command>"`, offline |
| What profile does this file have? | `python tools/ioguard.py profile <file>` |
| What did the guard decide in a session? | `${CLAUDE_PLUGIN_DATA}/events/<YYYY-MM>/<session>.jsonl` |
| Is the io server alive? | `${CLAUDE_PLUGIN_DATA}/sessions/<session>.alive`, written every 5 seconds |
| What did Claude Code itself do? | `claude --debug`, then `~/.claude/debug/` |

## Related

- `docs/design/architecture.md`: the design and every contract.
- `.claude/tasks/README.md` and `.claude/tasks/context.md`: the plan, the decisions and the evidence.
- `engineering`, `testing`, `verification` and `prose`: the kit's rules for every project.
