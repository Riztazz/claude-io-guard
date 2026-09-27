---
title: Write the io-guard skill
stage: G
area: docs
created: 2026-09-27
status: open
depends-on: [11, 12, 17, 20, 24, 25]
findings: [RUN-1]
platforms: [windows, macos]
commit: "docs: the io-guard skill, with its codes, fixes and the tool for each job"
---

## Why

Every refusal from the guard names a code and a tool. When a refusal arrives, the model needs one short reference
to read, not a page of rules. MCP tools sit behind tool search by default, so a refusal that says "use io.edit"
sends the model to a tool it has not loaded yet.

## What to build

`plugins/io-guard/skills/io-guard/SKILL.md`, under 150 lines:

- A `description` that makes the skill load when an io-guard code appears.
- **The code table, generated from `CODES`**, with each code's meaning and fix. The generator runs in CI, and the
  build fails when the page and the table differ.
- **The tool table, generated from `ToolRegistry.markdown()`.** Which tool does which job: Edit, Write, `io.edit`,
  `io.splice`, `io.append`, `io.run` and `io.format`, each by its callable name, such as
  `mcp__plugin_io-guard_io__io_edit`, and the ToolSearch step that loads it.
- What the guard fixes on its own, how it reports each fix, and the rewrite modes (D12).
- How to wait for a long run without sleep chains (RUN-1).

## Where

`plugins/io-guard/skills/io-guard/SKILL.md`, and its generator in `ioguard/cli/`.

## Done when

- `/skill-doctor` lists the skill and shows its context cost.
- A test session on Windows that triggers five different refusals recovers from each one in a single retry. Count
  the retries in the session's transcript.
