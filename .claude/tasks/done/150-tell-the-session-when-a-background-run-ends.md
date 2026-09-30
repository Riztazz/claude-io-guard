---
title: Tell the session when an io.run background run ends, as a background Bash call does
stage: I
area: mcp
created: 2026-09-30
status: done
depends-on: []
findings: [RUN-2, RUN-5]
platforms: [windows, macos]
commit: "docs: a long wait goes to the Bash tool's run_in_background"
---

## Why

Raised by the lead on 2026-09-30, from this repository's own sessions, which ran every long job through
`io.run` with `background: true` for a day.

A Bash call with `run_in_background` is Claude Code's own background task. The desktop app lists it under
Background tasks, and when it ends Claude Code wakes the model with a task notification, so nothing polls.
`io.run` with `background: true` returns a handle, and Claude Code knows nothing of it:

- no entry in the app's Background tasks,
- no notification when it ends, so the model polls `io.status` or sleeps in between, which costs turns and
  tokens, and a run that ends while the model waits on something else goes unseen until the next poll,
- a foreground `io.run` past about 3 minutes was cut off in this repository's session of 2026-09-29 and 30,
  seen and not measured, so the long jobs had to go to the background, where the problem above starts. The
  Claude Code docs say "An MCP call still running after 2 minutes moves to the background" (`context.md`,
  "Doc facts"), which no probe has checked yet.

An agent that takes io-guard's advice and moves a long command from Bash to `io.run` loses the notification.

## Is it fixable

Not in full from the server alone. An MCP tool cannot make a Claude Code background task, and a server-sent
message does not wake the model: the probes found no client that shows progress notifications
(`context.md`, "Hooks and MCP", row 16). What io-guard can do, cheapest first:

1. **Say it at the next hook.** The server knows when a run's process ends (`proc.Pump.done`). Every later
   hook call, a PreToolUse, a PostToolUse or a UserPromptSubmit, can add one line of context: `io.run <handle>
   ended with exit 0 after 312 s. Read its log with io.read_log.` That reaches the model on its next tool call
   or turn, with no poll, but it does not wake an idle session.
2. **Hand the wait to Claude Code.** A background `io.run` answers with a one-line Bash command the model runs
   with `run_in_background`, such as a small waiter script in the plugin that exits when the run's handle
   ends. Claude Code then owns a real background task: it shows in the app, and its end wakes the model with a
   notification. The run itself stays in io-guard, byte-exact and under the user's rules. The cost is one
   extra Bash call per background run, which io-guard's own hooks check like any other.
3. **Leave long runs to the Bash tool.** Say in the tool description and the skill that a run the model will
   wait on for minutes goes through Bash with `run_in_background`, and `io.run` is for bodies with backslashes
   or quotes. The cheapest, and it gives up io.run's byte-exact transport for exactly those runs.

## What to build

- A probe first: what a foreground `io.run` does at 2 minutes and at 3 on the CLI and the desktop, and whether
  a server-sent `notifications/message` or progress shows anywhere. Record both in `docs/live-checks.md`.
- Then option 1, and option 2 if the lead picks it. The lead decides between 2 and 3.

## Where

`mcp/tools_run.py` (`started`, `status`), `hooks/entry.py` or the bridge for the next-hook line,
`lib/proc.py` (`Pump`), the skill page, and a waiter script under `plugins/io-guard/scripts/` for option 2.

## Done when

- A background `io.run` that ends while the model works on something else is named in the next hook's
  context, once, and a test shows it.
- With option 2, the desktop app lists the wait under Background tasks, and its end wakes the session, seen in
  a live probe.

## What changed

The lead picked option 3 on 2026-09-30, recorded as D47 in `context.md`. Options 1 and 2 were not built, and
neither was the probe of a foreground `io.run` past 2 minutes, which option 3 no longer needs.

io-guard's own texts were the reason agents moved long waits to `io.run`: the skill's rule said "Wait for a
long run with `io.run` in the background and `io.status`", and `io.run`'s description offered itself "for a long
run". Both now send the wait to the Bash tool:

- `mcp/tools_run.py`: `io.run`'s description says to use it for a script body or an argument with backslashes
  or quotes, and to send a run to wait on for minutes to the Bash tool with `run_in_background`, which Claude
  Code tells the session about when it ends. The `background` field says nothing tells the session when a
  background `io.run` ends.
- `plugins/io-guard/skills/io-guard/SKILL.md`: the rule row and "Wait for a long run" put the Bash tool's
  `run_in_background` first, and `io.run` with `background` second, for a body that must arrive byte for byte,
  where the model asks `io.status` itself.

The test: `test_io_run_and_the_skill_send_a_long_wait_to_run_in_background` in `tests/mcp/test_tools_run.py`
reads `io.run`'s description and the skill's "Wait for a long run" section. It failed first on all four of
its checks, then passed.

Evidence:

- `python tests/run_all.py`: 1,125 tests, OK, 2 skipped, against 1,124 at task 151.
- `python tools/skill.py --check` exits 0, so the skill's generated tables still match.
- `live-run-tools`, `live-server`, `live-skill-doctor` and `live-empty` passed on the CLI 2.1.283. The server
  lists `io.run` with its new description, and the skill still loads at its old size.

Not checked: whether a model given the new texts picks the Bash tool for a long wait. The texts are what it
reads, and no probe measures its choice.

Docs: `docs/tools.md` says why a long wait goes to Bash, `docs/design/architecture.md`'s `io.run` section says
the same, and `.claude/tasks/context.md` holds D47.

Checked on Windows 10 on 2026-09-30.
