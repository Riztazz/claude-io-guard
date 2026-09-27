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
  - task 06: the server and `hook.sh` start
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
- **Sandbox.** With the sandbox on, check that the plugin data folder and the scratchpad accept writes. Document any
  `sandbox.filesystem.allowWrite` entry the guard needs.

## Where

`plugins/io-guard/scripts/ioguard/`, `tests/`, `docs/compat.md`, `docs/live-checks.md`.

## Done when

- Every deferred check above passes on the lead's Mac, with the Claude Code version recorded.
- CI is green on the macOS runner.

## Notes

- Waits for the lead's Mac (D21). Until then, code assumes the Mac has Python 3.14 installed.
