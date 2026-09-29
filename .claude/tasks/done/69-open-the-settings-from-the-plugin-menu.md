---
title: Open the settings page from the plugin menu
stage: I
area: skills
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [33]
findings: []
platforms: [windows, macos]
commit: "feat: a settings entry in the plugin menu opens the settings page"
---

## Why

On 2026-09-29 the lead asked for a button in the desktop app's plugin menu that opens the settings page. The
menu, Plugins > Io guard, lists the plugin's skills: it showed the one skill, `io-guard`, in the lead's
screenshot. A plugin has no other kind of entry there, so a second skill is the button.

## What to build

- `skills/settings/SKILL.md`: the skill the menu lists as `settings`, also run as `/io-guard:settings`. It
  tells the model to call `io.dashboard`, open the URL in the browser pane, and say which checks are off.
- A test that each plugin skill is named for its folder and names only tools the server has.
- A live probe that runs `/io-guard:settings` and sees `io.dashboard` answer with a URL.

## Where

`plugins/io-guard/skills/settings/SKILL.md`, `tests/test_plugin_files.py`, `tools/probes/run_probe.py`.

## Done when

- Picking `settings` under Io guard in the plugin menu opens the settings page.

## What changed

- `plugins/io-guard/skills/settings/SKILL.md`, new: three steps, `io.dashboard`, the browser pane, and two lines
  on what is off and when the page stops. It loads the deferred tool first, and falls back to giving the URL
  where there is no browser pane.
- `tests/test_plugin_files.py` (1): every skill's `name` is its folder, it has a description, and every
  `mcp__plugin_io-guard_io__` tool it names is one the server registers.
- `tools/probes/run_probe.py`: `live-settings-skill`, prompt `/io-guard:settings`, 16 turns.
- Docs: `README.md` (Configure it), `docs/design/architecture.md` (the tree), `docs/compat.md`, `CLAUDE.md`.

Evidence:

- `python tests/run_all.py` from Git Bash ran 893 tests, all passing, up from 892.
- `live-settings-skill` passed on 2.1.281 and 2.1.283 on Windows on 2026-09-29. The skill loaded
  `io.dashboard` and called it, and the session answered with the URL, that no check was off, and that the
  page closes after 5 minutes. Haiku searched for the tool seven times before its first call, which ran out
  the first run's 8 turns.
- Not seen: the menu entry itself in the desktop app. It needs this commit installed and the app restarted.
