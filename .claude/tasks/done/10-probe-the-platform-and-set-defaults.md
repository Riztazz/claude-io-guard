---
title: Probe the platform at session start and set safe defaults
stage: B
area: transport
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [03, 08]
findings: [SHW-4, SHL-2, SHL-3, OUT-4, OUT-5, STL-3]
platforms: [windows, macos]
commit: "feat: learn the platform at session start and give every shell UTF-8 defaults"
---

## Why

Several checks depend on the platform:
- The backslash halving and the 8 KB cut exist on Windows only (#92543).
- The Windows budget shrinks as the command wrapper grows (#95653).
- A cp1252 console crashes Python prints: 34 charmap errors, and one live while this plan was written.

A SessionStart probe measures once, and every later check reads the result.

## What to build

A SessionStart check, run as a command hook through `hook.sh`, because `CLAUDE_ENV_FILE` belongs to a hook
process. It writes `${CLAUDE_PLUGIN_DATA}/probe.json` with the `Probe` fields in `docs/design/architecture.md`,
section 2:
- the OS, and the Claude Code version where the event exposes it
- which tools are present: Git Bash and its version, pwsh, python, git
- Python's console encoding, and whether the file system ignores case
- the project's dirty files at session start, for STL-3 and task 19

It also sets two things for later checks:
- **The transport budget.** On Windows the default is 6,000 bytes of command, counting each apostrophe as 4 bytes,
  and `transport.budget_bytes` configures it. `SessionState.budget_override` holds a lower value that task 22
  learns from a failure. On macOS there is no budget unless task 36 finds one. When a Claude Code version fixes
  #92543, the probe's version check retires the rule.
- **Environment defaults for later shell calls.** Set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` everywhere. On
  Windows, also set `DOTNET_CLI_UI_LANGUAGE=en` and `VSLANG=1033`. There are three routes:
  1. `CLAUDE_ENV_FILE`, if task 03 confirms it
  2. otherwise a prefix that task 11 adds to the Python commands it rewrites
  3. otherwise a settings `env` block in the README's snippet (task 34)

**Do not set `MSYS_NO_PATHCONV=1` globally.** Agents run `python /c/Users/...` hundreds of times, and those paths
need Git Bash's conversion. Task 14 handles slash arguments one command at a time.

## Where

`plugins/io-guard/scripts/ioguard/checks/session_probe.py`, `lib/platform.py`, and
`${CLAUDE_PLUGIN_DATA}/probe.json` at run time.

## Done when

- `probe.json` is written at session start on Windows, in under 300 ms.
- On Windows, a Python run through the Bash tool prints U+2192 without an error, once the defaults apply.
- Task 19 can read the list of files that were dirty at session start.
- The probe's tests pass in CI on both platforms. Its live run on the Mac waits in task 36.

## What changed

- **`checks/session_probe.py`**, the first registered check. At SessionStart it measures the machine,
  writes `probe.json`, and appends the shell defaults to `CLAUDE_ENV_FILE`, keeping another hook's lines and
  adding nothing twice. Its keys `checks.session.probe.env` and `env_windows` are the user's alone, because a
  variable such as `PYTHONSTARTUP` runs a program (D24). A name a shell cannot export is left out and named in
  one user message.
- **`lib/probing.py`**, the measuring half: `tool_version`, `find`, `claude_version`, `console_encoding`,
  `case_insensitive`, `this_python`. A tool runs `--version` in its own folder, and a `ToolVersion` now carries a
  `stamp`, so an unchanged tool keeps its version without running again.
- **The Claude Code version** comes from `AI_AGENT` in the hook's environment, then `CLAUDE_CODE_EXECPATH`,
  because the SessionStart event names none.
- **The transport budget, split in two.** `Probe.transport_budget` is the Bash tool's cut on Windows, 7,807
  bytes with each apostrophe counted as four, measured in the baseline, and `halving` is true, both until
  `FIXED_IN` names the release that fixes #92543. The policy margin, `transport.budget_bytes` at 6,000, enters
  with task 11, which reads it, and task 11 now says it takes the smallest of the key, the cut and the learned
  override.
- **`Context` gained `env` and `data_dir`**, so no check reads `os.environ`, and `FsPort` gained
  `make_folders`, because a fresh install has no data folder yet. `Probe.dirty_at_start` is None when git cannot
  answer, `()` outside a repository, and `Probe.to_json` writes what `from_json` reads.
- **`tools/probes/run_probe.py`:** the `live-probe` probe, and a guard run keeps the session's `probe.json`.
- **Tests, 255 in all, up from 227:** `tests/lib/test_probing.py`, `tests/checks/test_session_probe.py`, and
  two more in `tests/lib/test_context.py`.
- **Docs:** `docs/design/architecture.md` sections 1 and 2, `context.md` rows 23 and 24, `docs/compat.md`,
  `docs/live-checks.md`, `README.md` (the shell defaults), `CLAUDE.md`, the `io-guard-dev` skill and task 11.
  The drawing already has the session probe.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **`live-probe`, CLI 2.1.283 and the desktop's 2.1.281:** `probe.json` named bash 5.2.37, pwsh 7.6.6, git
  2.49.0, the console's cp1252 and the running release. The probe itself took 143.4 ms the first time and 54.1
  and 56.8 ms once it kept the versions. Bash's `python -c "print(chr(0x2192))"` printed the arrow, and the
  same command under `env -u PYTHONUTF8 -u PYTHONIOENCODING` failed with `UnicodeEncodeError` from cp1252.
- **The dirty list:** the probe listed the checkout's modified and untracked files as full paths, which task 19
  reads from `ctx.probe.dirty_at_start`.
- `python tests/run_all.py` ran 255 tests, all passing.

Not checked:

- **The whole hook under 300 ms.** The probe is, but `hook.py` also starts Python and checks the server's
  interpreter, so the process took 245 to 343 ms from start to exit.
- **PowerShell calls.** `CLAUDE_ENV_FILE` does not reach them (`context.md`, row 23). Their Python printed the
  arrow anyway, so routes 2 and 3 were not needed for it, and no other PowerShell program was tried.
- **macOS.** CI runs the tests, and the live run waits in task 36.
