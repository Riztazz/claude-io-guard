---
title: Write the io-guard skill
stage: G
area: docs
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
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

## What changed

- **`plugins/io-guard/skills/io-guard/SKILL.md`**, 119 lines, description 365 characters. A card of six rules,
  the tool table, what io-guard fixes on its own with each fix's code, the rewrite modes and their defaults
  (D12), how to wait for a long run with `io.run` in the background, `io.status` and `io.read_log` instead of
  sleep chains (RUN-1), and the code table.
- **The two tables are generated.** `ToolRegistry.markdown()` gives the tool table: each io tool's job, its
  name and its callable name, the hook tools left out. `mcp/skill.py` writes it and the code table from
  `CODES`, sorted by code, between the page's marker lines, and `python tools/skill.py [--check]` runs it.
  `tests/mcp/test_skill.py` fails while the shipped page differs from what the declarations give, so CI
  stops a new code or tool that ships without its row.
- **The generator sits in `mcp`, not `cli`.** The tool table needs the tool registry, and `cli` never imports
  `mcp` (`tests/test_layout.py`). `tools/skill.py` imports `ioguard.mcp.skill`, which the layout rule in
  `architecture.md`, section 1, and the `io-guard-dev` skill now allow.
- Tests: 679 before, 685 after, all passing, from `python tests/run_all.py`.
- **Evidence.** `live-skill-doctor` passed on the desktop's 2.1.281 and the CLI 2.1.283: `/skill-doctor`
  lists `io-guard:io-guard` at under 20 tokens a turn. `live-skill` passed on both: in dontAsk mode, five turns
  met `SHELL_WRITE`, `MSYS_PATH`, `TRAILING_BACKSLASH_QUOTE`, `POWERSHELL_TRAP` and `DIALECT_MISMATCH`, and
  Haiku's next call in each turn ran, one retry each, counted from the session's stream. Haiku loaded no skill,
  so the refusal text did the work. The first 2.1.281 run failed its check because Haiku sent `tasklist /FI`
  to PowerShell and never met `MSYS_PATH`. It recovered from the other four in one retry. Earlier versions of
  the probe showed Haiku stepping around backticks in double quotes and `> nul` on its own, and replying DONE
  after a refusal when the turn asked for DONE, so the probe names a command to try first and asks for nothing
  after it.
- **Docs:** `docs/design/architecture.md` sections 1 and 7, the README's "Work on it", `docs/compat.md`,
  `docs/live-checks.md`, `context.md`, and `CLAUDE.md`'s layout and "Running things". The drawing's skill box
  already says the page is generated from the code table and the tool registry.
- Checked on Windows on 2026-09-28. Not checked: macOS, which waits in task 36, and a model other than Haiku.
