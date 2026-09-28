---
title: Add our evidence to the upstream plugin identity bug
stage: I
area: release
created: 2026-09-28
status: open
depends-on: [40, 41]
findings: []
platforms: [windows]
commit: "none, this is a comment on GitHub"
---

## Why

On 2026-09-28 the desktop app renamed io-guard to `io-guard@inline` after a restart, and its saved `python`
option and its data folder stayed behind under `io-guard@claude-io-guard` (tasks 40 and 41, `context.md`).
anthropics/claude-code#92427 already reports the option half, on macOS with the desktop's 2.1.260: "CLI and
desktop resolve different plugin identities". It is open, with no comment and no maintainer reply. Our
evidence adds a Windows repro, which plugins the desktop renames, when it starts, and that
`${CLAUDE_PLUGIN_DATA}` moves as well.

## What to build

- A comment on #92427, below. Nothing names the lead's own projects.

## Where

https://github.com/anthropics/claude-code/issues/92427

## Done when

- The lead has approved and posted the comment, and this file links it.

## Blocked on

The lead's approval, and the lead posts it: a comment on a public issue is the lead's to send.

## Draft, 2026-09-28

> Same on Windows 10: desktop app 2.9939.2 with its bundled Claude Code 2.1.281, and the CLI at 2.1.283.
> A few things this issue doesn't mention yet:
>
> **Which plugins get renamed.** At each session spawn the desktop reads `~/.claude/plugins/installed_plugins.json`
> and hands two kinds of plugin to the SDK as `{type: "local", path}`, which Claude Code names `<name>@inline`:
> every enabled plugin whose marketplace in `known_marketplaces.json` has a `directory` or `file` source, and every
> plugin synced from claude.ai. When `known_marketplaces.json` can't be read, it hands over every installed plugin.
> Plugins from other marketplaces are "left to the CLI's own loader" and keep their id. Our `main.log`:
> `[CCD] Passing 6 plugin(s) to SDK (skills: 1, remote: 4, local: 1)`. A synced plugin therefore runs as
> `<name>@synced` in the terminal and `<name>@inline` in the desktop, and this machine has both
> `plugins/data/superpowers-synced` and `plugins/data/superpowers-inline`.
>
> **When it starts.** Sessions reloaded inside a running desktop app kept `io-guard@claude-io-guard`, and its log
> read `local: 0`. After the app restarted it read `local: 1`, and every session got `io-guard@inline`.
>
> **The data folder moves too.** `${CLAUDE_PLUGIN_DATA}` follows the id, so the desktop copy and the terminal copy
> of one plugin keep separate state. For our plugin that was its user config and, worse, its lock files: two
> sessions editing one file each took a lock the other never saw.
>
> **What the empty option did.** Our `.mcp.json` used `"command": "${user_config.python}"`. Under `@inline` the
> option was empty, the default `python3` ran, which on Windows is the Microsoft Store stub, and the server exited
> in 195 ms with "Python was not found".
>
> **What helps.** `"<name>@inline": false` in `enabledPlugins` stops the session copy shadowing the installed one,
> as the plugin loading docs say. We checked that on the CLI with `--plugin-dir`, not yet in the desktop. On the
> plugin side we stopped depending on the id: no `userConfig`, an environment variable for the one setting, and a
> fixed folder in place of `${CLAUDE_PLUGIN_DATA}`.
>
> Any of these would fix it for plugin authors: pass the installed plugin's real id through the SDK, copy
> `pluginConfigs["<name>@<marketplace>"]` to the `@inline` id and resolve `CLAUDE_PLUGIN_DATA` from the real id
> when re-passing it, or leave installed plugins to the CLI's loader as the desktop already does for other
> marketplaces.
