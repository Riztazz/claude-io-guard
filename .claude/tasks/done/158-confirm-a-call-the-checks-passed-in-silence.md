---
title: A call the checks pass in silence looks the same as a call no hook saw
stage: I
area: hooks
created: 2026-09-30
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "feat: telemetry.confirm says the checks ran on a quiet call"
---

## Why

The lead asked an agent in another project, on 2026-09-30, whether Edit, Write and Bash came back with anything
from io-guard. It answered: "Read, Write, and Bash calls came with plain-text hook context this session, but all
~60 Edit calls returned only the default success message - so I can't tell if Edit hooks ran silently or didn't
run at all."

They ran. The day's telemetry holds a PreToolUse and a PostToolUse line for every Edit: 115 of each in
SmartTablesHost, 22 in CLICKER, 328 in this repository. The checks had nothing to say, and silence is what they
answer then. An agent, and the lead reading over its shoulder, cannot tell that from a hook that never fired.

The lead: "Its good option to have for debugging, add it, add to config, default false, user can set it to on,
in tooltip say it adds an extra line of context".

## What changed

A setting, `telemetry.confirm`, false by default. With it on, `hooks.entry.confirmed` adds one context line after
a tool call when at least one check ran and none said anything:

```
io-guard: 4 checks ran on this Edit, and none had anything to say.
```

- It speaks after the call only, at PostToolUse, so one tool use gets one line.
- A call a check spoke about keeps that check's lines and gets no other.
- A call no check ran on gets nothing.
- The settings page shows the key with its text: "Tell the agent after each tool call that io-guard's checks ran
  and had nothing to say. It adds an extra line of context to every such call, so turn it on only to see that
  the hooks run."

Evidence:

- `test_a_call_the_checks_pass_in_silence_is_confirmed_only_when_the_setting_is_on` in
  `tests/hooks/test_entry.py` failed first with no answer, and holds four cases: on and quiet, off, before the
  call, and a call a check spoke about.
- `python tests/run_all.py`: 1,141 tests, OK, 2 skipped, against 1,140 at task 157.
- Not seen live: the line in a session, and the key on the settings page. Both need the plugin updated and the
  app restarted.

Docs: `docs/settings.md` has a paragraph on it, and `docs/design/architecture.md` names the key and the function.

Checked on Windows 10 on 2026-09-30.
