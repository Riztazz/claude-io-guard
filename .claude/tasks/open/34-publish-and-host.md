---
title: Publish the plugin on GitHub and install it from claude.ai
stage: I
area: release
created: 2026-09-27
status: open
depends-on: [27, 31]
findings: []
platforms: [windows, macos]
commit: "docs: install and update instructions for io-guard"
---

## Why

Decision D1: the plugin is hosted at github.com/Riztazz/claude-io-guard and installed from claude.ai. Every machine
signed in to the lead's account then gets the plugin and its updates.

## What to build

1. **Scrub before any push that makes content public (D19).** Everything is published except the rows that came
   from the friend's scan, the EXT test-helper rows included. Remove them from `context.md`,
   `baseline/io_traps.html`, `baseline/io_findings_map.md` and any task that quotes them, then grep the tree for the
   word "friend" and for each removed id.
2. **Copy the kit snapshot in (D11).** The kit's links are gitignored, so a clone has no rules and no skills. Copy
   the kit's `rules/generic/` and `skills/generic/` into `docs/kit-snapshot/`, with the kit's date, as reading
   material. Never add the links themselves to git.
3. **Bring `README.md` up to date.** It exists from the handover. Check each section against what shipped:
   - what io-guard does, and the architecture picture
   - how to install it: from claude.ai under Customize > Plugins, or with
     `/plugin marketplace add Riztazz/claude-io-guard` and then `/plugin install io-guard@claude-io-guard`
   - requirements: Claude Code 2.1.281 or later, Python 3.14 or later, and `python` set once in
     `/plugin configure io-guard` on Windows (D15)
   - the settings snippet: `bashEditDiffEnabled: true`, `permissions.allow` for the read-only io tools,
     `ENABLE_TOOL_SEARCH=auto:5`, the commit and push rules from task 29, and the command-hook fallback from task 06
   - the rewrite modes and every other setting, and how to turn a check off
   - privacy: everything stays on the machine
4. **Versioning (D18).** No `version` until 1.0, so installs track commits. The 1.0 release gets the first tag and
   release notes.
5. **Push.** Each push needs its own grant from the lead.
6. **Add the marketplace in claude.ai.** Then check that it syncs on Windows, first in the desktop app's Code tab,
   which is the lead's main surface, then in the CLI. Confirm that auto-update is on.
7. **Optional, later: submit to Anthropic's directory.** Hooks and local MCP servers run only in Claude Code and
   Cowork, so the listing has to say so.

## Where

`README.md`, `docs/kit-snapshot/`, `.claude-plugin/`, `plugins/io-guard/.claude-plugin/plugin.json`.

## Done when

- The grep in step 1 finds nothing.
- The Windows machine loads io-guard, either synced from claude.ai or from the marketplace install.
- A live session on Windows shows a guard refusal. The Mac's check waits in task 36.
