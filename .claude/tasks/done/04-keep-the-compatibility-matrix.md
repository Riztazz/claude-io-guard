---
title: Keep the harness compatibility matrix and the live-check list
stage: A
area: docs
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
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

## What changed

- **`docs/compat.md`:** 22 features, each with the version it needs, the probe that confirms it and what
  io-guard does without it. It opens with the two commands that recheck them after a Claude Code update.
- **`docs/live-checks.md`:** 30 live facts in three groups, the file and shell tools, plugins, and hooks and
  MCP, each with the Windows version, the macOS state and the date. Its first section is the rule that a task
  running a live check updates its rows in the same change.
- **`tools/probes/run_probe.py`** gained `verdicts`, which checks each probe's latest run against its recorded
  result, and `IOPROBE_CLAUDE`, which picks the binary. Each summary now records the Claude Code version.
- **The 2.1.281 floor rests on the probes now.** Task 03 ran them on the 2.1.283 CLI only, and the design's
  reason, "the first release with `mcp_tool` hooks that wait for their server", is in no current doc. So every
  probe ran again on the desktop app's bundled `claude.exe` 2.1.281, and all 28 verdicts passed. The CLI rerun
  at 2.1.283 passed all 28 as well, after one fix to a verdict that was too strict (`context.md`).
- **The review's 2.1.76 for legacy elicitation is also in no current doc.** `compat.md` gives 2.1.281 for it,
  the oldest release probed, and gives the review as the source for URL-mode elicitation.
- **Docs:** `README.md` links both pages from its install steps and its "Work on it" section. `CLAUDE.md`
  names both pages and the probe commands. `docs/design/architecture.md`, section 13, gives the new reason for
  2.1.281. `context.md` records the reruns and their timings. The drawing needed nothing.

Evidence: `python tools/probes/run_probe.py verdicts` printed `pass` for all 28 probes on 2.1.281 (runs
20260927-1318 to 1320) and on 2.1.283 (runs 20260927-1321 to 1323). `mcp-prompts` on 2.1.283 printed `FAIL`
first, because the model asked for permission after the first denial and stopped. The harness had denied that
tool as expected. The verdict now checks every tool called, and the rerun denied all three.

Checked on Windows 10 on 2026-09-27, with the `claude` CLI 2.1.283 and the desktop app's bundled 2.1.281.

Not checked:

- **macOS.** Every macOS cell says "waits for the Mac" (D21).
- **Releases older than 2.1.281.** None is installed here.
- **The rows marked "not probed" in `compat.md`:** URL-mode elicitation, backgrounding after 2 minutes, and
  `userConfig` in `/config`. Their versions come from the docs or the design review.

Commit subject: `docs: the harness compatibility matrix and the live-check list`.
