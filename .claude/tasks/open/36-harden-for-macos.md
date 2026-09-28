---
title: Harden the guard on macOS, once the lead's Mac is back
stage: I
area: runtime
created: 2026-09-27
status: open
depends-on: [11, 12, 13, 17, 18, 23]
findings: []
platforms: [macos]
commit: "fix: the guard on macOS bash 3.2, BSD tools and APFS names"
---

## Why

Every live measurement so far comes from Windows, and the lead's Mac is down (D21). CI on the macOS runner proves the
unit tests, not what the harness does on a Mac. The Mac also brings traps of its own:

- `/bin/bash` 3.2, which lacks Git Bash 5 syntax such as `readarray` and `${x,,}`
- BSD tools: `sed -i ''`, `stat -f`, and no `grep -P`
- NFD file names on APFS
- case-insensitive paths
- the sandbox

## What to build

- **Run every deferred live check on the Mac**, with Python 3.14 installed there, and record each one in task 04's
  pages:
  - task 03: the Bash tool with a 9 KB command and `echo 'a\\b' | od -c`, and `bash --version` through the Bash tool
  - task 06 and D29: the server and the hooks start through `pyrun`, which keeps its executable bit through a
    clone, the plugin cache and the claude.ai sync, and `python3` on a Mac with only Apple's stub
  - task 08: `guard-fields`, `guard-large` and the four `live-*` probes, whose `python` option there is the Mac's
    own interpreter
  - task 10: the probe at session start
  - tasks 11, 16, 17, 20 and 21: their live checks
  - task 19: the `lsof` holder lookup
  - task 23: `/mcp` and the bridge
  - task 34: the plugin syncs from claude.ai and a refusal shows
- **Portable-subset lint.** Warn on bash 4+ syntax and on GNU-only flags when the probe (task 10) finds bash 3.2 or
  BSD tools.
- **Path comparisons.** Normalise Unicode to NFC before comparing paths. Ignore case where the file system does.
- **Sandbox.** With the sandbox on, check that io-guard's folder and the scratchpad accept writes. Document any
  `sandbox.filesystem.allowWrite` entry the guard needs.

## Where

`plugins/io-guard/scripts/ioguard/`, `tests/`, `docs/compat.md`, `docs/live-checks.md`.

## Done when

- Every deferred check above passes on the lead's Mac, with the Claude Code version recorded.
- CI is green on the macOS runner.

## Notes

- Waits for the lead's Mac (D21). Until then, code assumes the Mac has Python 3.14 installed.

## Blocked on

The lead's Mac, for every live check above and the sandbox.

## What changed so far

- **Portable-subset lint, built 2026-09-28.** `lib/portable.py` finds bash 4 syntax, `readarray`, `mapfile`,
  `coproc`, `${x,,}` and `${x^^}`, `declare -A`, `|&`, `&>>`, `;;&`, `globstar`, `${a[-1]}`, `${x@Q}` and
  `wait -n`, and GNU-only options: `sed -i` with no suffix, `grep -P`, `stat -c`, `date -d`, `find -printf`,
  `cp` and `mv -t`, `du -b` and `head -n` with a negative count. An operator counts only unquoted, and an
  expansion also in double quotes. `shell.lint` gives the new warning `NOT_PORTABLE` for the bash 4 forms when
  the session probe measured bash below 4, and for the GNU forms on macOS, three at most per command. Windows
  meets none of it.
- **Path names as APFS compares them.** `paths.resolved`, the key of the lock table and of `file_lock`, is NFC
  on macOS and folds case where the file system ignores it, so an NFD name and another spelling of one file
  share one lock. `normalise` already made names NFC, and `inside` already ignored case.
- **Estimate.** Read as if under bash 3.2 and BSD tools, 451 of the corpus's 58,779 recorded Bash commands
  (0.77%), all written on Windows, would be named: `sed -i` with no suffix 377, `stat -c` 45, `grep -P` 16,
  `find -printf` 8, `head -n -N` 3, `date -d` 2 and `declare -A` 1. Each is a form BSD's tool rejects or reads
  another way. The first version also named `|&` inside a double-quoted grep pattern, which is why operators
  now count only unquoted.
- Tests: 720 before, 729 after, all passing on Windows: `tests/lib/test_portable.py` 5, `test_lint.py` 3,
  `test_paths.py` 1. CI runs them on the macOS runner.
