---
title: Keep each session's start-of-session dirty list, taken once
stage: I
area: checks
created: 2026-09-28
status: open
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
