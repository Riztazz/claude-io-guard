---
title: Keep the harness compatibility matrix and the live-check list
stage: A
area: docs
created: 2026-09-27
status: open
depends-on: [03]
findings: []
platforms: [windows, macos]
commit: "docs: the harness compatibility matrix and the live-check list"
---

## Why

The design leans on harness facts, and the harness changes weekly. A feature that gates on nothing breaks silently
the week it changes, and a fact confirmed once and never again goes stale without anyone seeing it
(`docs/design/architecture.md`, section 13).

## What to build

- **`docs/compat.md`:** one row per harness feature the plugin uses. The Claude Code version that introduced it, the
  probe that confirms it, and what the plugin does when it is absent. Seed it from task 03 and the doc facts in
  `context.md`: `mcp_tool` hooks that wait for their server (2.1.281), `updatedInput` with `ask`, `bashEditDiff`,
  `updatedToolOutput`, `CLAUDE_ENV_FILE`, the legacy `elicitation/create` (2.1.76), URL-mode elicitation
  (2.1.281), `MCP_PROTOCOL_NEGOTIATION`, plugin sync from claude.ai (2.1.273).
- **`docs/live-checks.md`:** one row per live fact the design leans on, with the platform, the Claude Code version,
  the date of the last confirmation and the probe that confirms it.
- **The rule for later tasks:** every task that runs a live check updates its rows in the same change.

## Where

`docs/compat.md`, `docs/live-checks.md`.

## Done when

- Every item from task 03 has a row in one of the two pages.
- The minimum Claude Code version, 2.1.281, is justified by a row.
- `README.md` links both pages.

## Notes

- macOS rows say "waits for the Mac" until task 36 confirms them (D21).
