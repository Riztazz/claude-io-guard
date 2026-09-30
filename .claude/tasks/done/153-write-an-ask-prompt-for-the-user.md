---
title: An ask prompt reads as a warning to the user, and carries advice meant for the model
stage: I
area: hooks
created: 2026-09-30
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: an ask prompt is written for the user who answers it"
---

## Why

The lead set `transport.rewrite_mode.auto` to `ask` on 2026-09-30 and ran a heredoc in the desktop app, on
Claude Code 2.1.283. The prompt showed, under "Allow Claude to run ...?":

```
BODY_MOVED_TO_FILE: io-guard moved a 0.1 KB heredoc body to C:/Users/felia/AppData/Local/Temp/claude/
C--Users-felia-Desktop-projs-claude-io-guard/7eeb509f-.../scratchpad/io-guard/body-05a1ba37bf3e4608.txt, and
the command reads it from there. The body arrives exactly as written, with no backslash halved.
```

The lead: "can we also make the msg a little bit less scary?", then "We need to update all ASK messages, not
just this one".

Three things made it read as a warning: a capital code first, a long path the command box under it repeats, and
"halved". The text was the model's line, `CODE: note`, shown to a person. A check's own ask was worse: it ended on
the code's advice for the model, such as "Wait for the user's answer, and run nothing else in its place."

## What changed

`hooks/answer.py` writes an ask's `permissionDecisionReason` for the user, in `asked`. Every other answer is for
the model and leads with the code, as before.

- A rewrite's lines open with one line: "io-guard changed how this call is written, and it does the same thing."
- Each rewrite's note follows as `note (CODE)`.
- A check's result follows as `message (CODE)`, with no advice. That covers `RULE_ASKED`, `RESTORE_ASKED`,
  `TRUST_ASKED` and `CONFIG_ASKED`, and a warning another check adds to an asked call.

`BODY_MOVED_TO_FILE`'s note changed in every mode. It names the file by its name, since the command holds the
whole path. It says "The body is unchanged, and every backslash arrives as written." A body under 1 KB is sized
in bytes, where it said "0.0 KB".

The prompt for the lead's command now reads:

```
io-guard changed how this call is written, and it does the same thing.
io-guard moved a 96-byte heredoc body to the file body-05a1ba37bf3e4608.txt, and the command reads it from
there. The body is unchanged, and every backslash arrives as written. (BODY_MOVED_TO_FILE)
```

Evidence:

- Three tests failed first: `test_an_ask_says_what_happens_and_ends_on_its_code_with_no_advice` and the ask case
  of `test_ask_and_allow_carry_the_rewritten_input_and_the_note` in `tests/hooks/test_answer.py`, and the note's
  text in `tests/checks/test_transport_body.py`. The byte size failed first as "0.0 KB".
- `python tests/run_all.py`: 1,136 tests, OK, 2 skipped, against 1,135 at task 152.
- Seen live on 2.1.283 in the desktop app, before the change: a hook's `ask` shows its prompt in auto mode, with
  the rewritten command under the reason. The model gets no line of the reason.
- Not seen live: the new text in a prompt. The installed plugin is the old one until it is updated and the
  session restarts.

Docs: `docs/design/architecture.md`, section 6, says an ask's reason is written for the user. `README.md` shows
the new `BODY_MOVED_TO_FILE` note. `docs/live-checks.md` and D48 in `context.md` record the auto-mode prompt.

Checked on Windows 10 on 2026-09-30.
