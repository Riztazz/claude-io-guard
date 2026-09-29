---
title: Bound what a repository can make the hooks skip: config size, git time, and repeated overruns
stage: I
area: hooks
created: 2026-09-29
status: done
depends-on: []
findings: [security-review-2026-09-29-6]
platforms: [windows, macos]
commit: "fix: a repository cannot quietly make every hook skip its checks"
---

## Why

Fable's security review of 2026-09-29, finding 6, medium, checked in the code the same day. The pipeline fails
open by design (D7): a check that raises or overruns is skipped. A repository can provoke that on purpose.
`lib/config.py` and `lib/bytesio.py` read a config file whole with no size cap. Each git call gets 10 s
(`lib/git.py`), and `checks/touched.py` and `checks/shell_writes.py` make several per hook. `lib/git.py` decodes
status strictly, so a file name that is not UTF-8 raises. The user hears one `GUARD_ERROR` per session, and calls
then run unchecked.

## What to build

- Refuse a config file over a cap, such as 256 KB, as a load error that names the file.
- Inside a hook, git calls share the pipeline's budget rather than 10 s each.
- Decode git's output with `errors="replace"` where a path is only shown, and name the file where it matters.
- Count overruns and errors per session, and tell the user once when checks were skipped more than a few times,
  naming the check.

## Done when

- A huge config, a slow git and a non-UTF-8 file name each give one message that names the cause, and tests
  cover each.

## What changed

- `lib/config.py`: `read_file` reads at most `FILE_LIMIT` (256 KB) plus one byte, and a bigger file is a
  load error naming the limit, so the loader drops it whole and the existing load message names it.
  `mcp/tools_dashboard.py` `read_raw` refuses such a file the same way.
- `lib/git.py`: `Git.within(seconds)` gives a git whose every call ends by then. `time_left` gives each call
  the smaller of its own timeout and what is left, and raises `GitError` without starting git once the
  deadline has passed. Paths decode with `surrogateescape`, so a file name that is not UTF-8 parses, and its
  bytes go back to the file system unchanged. `GitPort`, `FakeGit` and replay's `SnapshotGit` gain `within`.
- `checks/pipeline.py`: `Pipeline.run` hands the checks `ctx.git.within(hard_ms)`. A check skipped for the
  budget `SKIPS_TOLD` (3) times in a session is named once in a `user_message` with `BUDGET_EXCEEDED`, saying
  to raise `pipeline.hard_ms` or turn the check off. A check that raises was already named once per session
  with `GUARD_ERROR`. `lib/context.py`: `SessionState.count`.
- Docs: `docs/design/architecture.md` (the budget step, git.py, the config loader). The README states none
  of this.

Evidence:

- `python tests/run_all.py`: 947 tests, OK, up from 941. New: a config file over the limit is dropped with
  the limit named, and one at the limit loads. A Latin-1 file name parses with its bytes kept. A git call
  past its deadline raises and starts nothing, and one within gets at most what is left. A check skipped on
  every call is named to the user once, on the third call. The pipeline hands git the 2 s hard budget.
- Live, Claude Code 2.1.283 on Windows: `live-empty` and `live-touched`, whose hooks call git, pass
  (20260929-125843, -125907).

Checked on Windows 10 on 2026-09-29. Not checked: a real slow git live, and a non-UTF-8 name on macOS, where
it can exist (task 36). Windows git writes every path as UTF-8.
