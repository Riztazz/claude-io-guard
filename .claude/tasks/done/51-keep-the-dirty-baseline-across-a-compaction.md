---
title: Keep each session's start-of-session dirty list, taken once
stage: I
area: checks
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [19, 41]
findings: []
platforms: [windows, macos]
commit: "fix: keep the dirty list per session, taken at its first start"
---

## Why

`write.location` tells the agent, once per file, that a file "already had uncommitted changes when this session
started" (`checks/location.py`, `dirty`, lines 113 to 119). In CLICKER on 2026-09-28 it said so of
`Source/CLICKER/NetSphere/NetIndex.h`, a file the same session, `0184073d-fc65-49ec-ad51-ff443f3c879f`, created on
2026-09-27. The agent's own earlier work read as the lead's.

The cause is where the list lives. `session.probe` runs at every SessionStart, and `hooks/hooks.json` gives that
hook no matcher, so it runs on startup, resume, clear and compact. Each run writes `dirty_at_start` into
`probe.json` (`checks/session_probe.py:128`). That is one file in io-guard's folder for every session and every
project on the machine. Each io server reads it once per session and project, on its first hook
(`hooks/entry.py:45`, `lib/context.py:329`).

Two things go wrong:

1. A session that starts again takes its list again. The CLICKER session ran across the desktop restart on
   2026-09-28. A SessionStart after the restart, a resume or a compaction, took a list that held the files that
   session wrote the day before.
2. A session in one project overwrites another's list. This repository's compaction at 14:59 local time on
   2026-09-28 left `probe.json` holding this repository's 16 dirty files. A CLICKER server that loads it next
   gets none of CLICKER's, and names nothing.

io-guard's hooks kept answering after that compaction, so the server itself is not at fault.

## What to build

- Keep the dirty list apart from the machine's facts. It goes in one file per session id under `sessions/`,
  written only when that session has none, and removed with the session's `.alive` and `.warned` files.
  `probe.json` keeps only what is true of the machine.
- `write.location` reads the list of the event's session.
- A live check: whether a resume and a compaction keep the session id, and which `source` each SessionStart
  carries. Record both in `docs/live-checks.md` and `docs/compat.md`. If a resume gets a new id, carry the list
  across by the transcript the two ids share, or say in this file why not.
- Tests: two sessions started in two projects keep their own lists. A second SessionStart of one session keeps
  the first list.

## Where

`plugins/io-guard/scripts/ioguard/checks/session_probe.py`, `lib/context.py` (`Probe`, `load_probe`),
`checks/location.py`, `hooks/entry.py`, `tests/`.

## Done when

- After a desktop restart resumes a session, and after a `/compact`, a file the session changed before gets no
  "when this session started" line. A file that was dirty before the session's first start still gets one.
- A session started in another project leaves this session's list as it was.

## What changed

- `lib/context.py`: `Probe` no longer holds `dirty_at_start`, so `probe.json` holds only the machine's facts. An
  old `probe.json` with the key still loads. `SessionState.dirty` and `dirty_at_start()` read
  `sessions/<session>.dirty` once it exists, and keep it.
- `checks/session_probe.py`: `measure` takes the dirty files only when the session has no list yet, in the same
  thread pool as the tools' versions. `run` writes the list once per session id. A git that cannot answer
  writes no file, never an empty list.
- `checks/location.py`: `dirty` reads `ctx.session.dirty_at_start()`.
- Tests: `tests/checks/test_session_probe.py` (5 on the list, 1 that `probe.json` holds none of it), and
  `tests/checks/test_location.py` and `tests/lib/test_context.py` moved off the probe field.
- Docs: `docs/design/architecture.md` (the `Probe` fields, the session files), `docs/live-checks.md` and
  `.claude/tasks/context.md` (row 40).

Evidence:

- `python tests/run_all.py` ran 830 tests, all passing, up from 826.
- Live, on 2.1.281 and 2.1.283, with `claude -p` and io-guard from this checkout: a start, a resume and a
  `/compact` of one session all ran under one session id, as `SessionStart:startup`, `resume` and `compact`.
  In a repository where `a.txt` was dirty before the start and `b.txt` appeared after it, the session was
  compacted, resumed and wrote both. The kept list held `a.txt` alone, `a.txt` got the "when this session
  started" line, and `b.txt` did not.
- Checked on Windows on 2026-09-28. The macOS live check waits in task 36.

Not built: removing the list with the session's other files. Nothing sweeps `sessions/`, so its `.alive`,
`.warned` and now `.dirty` files stay. Each is under a kilobyte.
