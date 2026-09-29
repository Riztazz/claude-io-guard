---
title: Put All projects and this project side by side on the settings page
stage: I
area: ui
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [33, 70]
findings: []
platforms: [windows, macos]
commit: "feat: the settings page puts all projects and this project side by side"
---

## Why

On 2026-09-29 the lead found the settings page's model wrong: the user's value sat at a card's top right, and the
project's "Same as yours / Override" and its control landed in a different place on each kind of setting. The
lead picked layout A of three mockups, two columns with the same control in the same place on every row, and
found "Yours, every project" confusing as a name.

## What changed

- `ui/dashboard.html`: each setting is a row of three columns under headings that stay at the top: the setting,
  "All projects" and "Only <project>". The headings' tooltips name each file. A project that sets nothing shows
  the value it takes, greyed, with "Same as all projects" and "Change for this project". An override has "Use
  all projects' value", and your own value has "Use the default". A list or a JSON value, and any page narrower
  than 640 pixels, stack the two columns under the setting with a heading each.
- "Change for this project" starts from the first value the project may pick. It started from the default,
  which a project may not pick in bypassPermissions mode, so the write was refused.
- `mcp/tools_dashboard.py`: `READ_BY` puts `commit_policy`'s keys under the `commit.policy` check, where two
  groups named `commit_policy` and `commit.policy` stood. The page names a global key by what follows its first
  dot.
- Tests: `tests/mcp/test_tools_dashboard.py` checks the merged group.
- Docs: `.claude/tasks/context.md` (D36), `docs/design/architecture.md` (the page) and `README.md` (the two
  columns).

Evidence:

- The page from this checkout in the browser pane, over copies of the lead's configs: 87 settings, one
  `commit.policy` group, and no stray text. At 1,100 pixels the columns lined up under their headings, and at
  the pane's 525 they stacked. Change for this project on auto mode wrote "refuse" and showed its control, on
  bypassPermissions mode it started at "refuse" with no refusal, and Use all projects' value undid both. The
  copy's project file then matched the original.
- `python tests/run_all.py` ran 904 tests, all passing.
