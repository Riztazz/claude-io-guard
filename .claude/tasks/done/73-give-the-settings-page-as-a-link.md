---
title: Give the settings page's URL as a link that opens in the user's own browser
stage: I
area: ui
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [69]
findings: []
platforms: [windows, macos]
commit: "feat: the settings skill links the page, token included"
---

## Why

On 2026-09-29 the lead asked for `/io-guard:settings` to also give a clickable link, token and all, so the page
opens in their own browser as well as in the browser pane.

## What changed

- `skills/settings/SKILL.md`: a step gives the whole URL as a Markdown link whose text is the URL itself, and the
  pane step no longer carries the fallback.
- `mcp/tools_dashboard.py`: the tool's note says the same, for a call made without the skill.
- `tools/probes/run_probe.py`: `live-settings-skill` passes only when the reply holds the link with its token.
- Docs: `docs/design/architecture.md` (where the page opens) and `README.md` (the link).

Evidence:

- `python tools/probes/run_probe.py run live-settings-skill` on Claude Code 2.1.283, then `verdicts`: pass. The
  run's reply held the page's URL as a Markdown link with its token.
- `python tests/run_all.py` ran 903 tests, all passing.
