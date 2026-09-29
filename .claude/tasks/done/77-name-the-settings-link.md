---
title: Name the settings page's link, so its token stays out of sight
stage: I
area: ui
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [73]
findings: []
platforms: [windows, macos]
commit: "feat: the settings link reads Open io-guard's settings page"
---

## Why

On 2026-09-29 the lead asked for the link `/io-guard:settings` gives to read as a plain link, with the token
out of sight, where task 73 had made the whole URL the link's text.

## What changed

- `skills/settings/SKILL.md` and the note `io.dashboard` returns: the link reads "Open io-guard's settings page",
  and its target keeps the whole URL with the token.
- `tools/probes/run_probe.py`: `live-settings-skill` passes only on a link with that text.
- Docs: `docs/design/architecture.md` (where the page opens) and `README.md` (the link).

Evidence:

- `python tools/probes/run_probe.py run live-settings-skill` on Claude Code 2.1.283, then `verdicts`: pass. The
  reply held `[Open io-guard's settings page](http://127.0.0.1:<port>/?token=<token>)`.
- `python tests/run_all.py` ran 911 tests, all passing.
