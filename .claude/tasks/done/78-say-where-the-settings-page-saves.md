---
title: Say on the settings page which file it saves in
stage: I
area: ui
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [76]
findings: []
platforms: [windows, macos]
commit: "feat: the settings page says which file it saves in"
---

## Why

On 2026-09-29 the lead turned a project's `commit_policy.ascii_only` off on the page and found the repository's
`.claude/io-guard.json` unchanged. The write had gone into the lead's own `config.json` under `projects`, as task
76 made it, and the page named that file only in a heading's tooltip.

## What changed

- `ui/dashboard.html`: a line above the column headings, at every width, names the user's `config.json` and says
  the project column saves in the same file, under `projects`, never in the repository's file.
- Docs: `docs/design/architecture.md` (the page). The README already says where each column saves.

Evidence:

- The page from this checkout in the browser pane, over copies of the lead's configs: the line read "Saved in
  <copy>/home/config.json. Only claude_io_guard saves in the same file, under projects, and never in the
  repository's .claude/io-guard.json.", above the headings.
- `python tests/run_all.py` ran 911 tests, all passing.
