---
title: Verify the hook and MCP features the design relies on
stage: A
area: runtime
created: 2026-09-27
status: open
depends-on: [02]
findings: [SHW-2, SHW-4, BYT-1, ANC-4, BYT-4]
platforms: [windows]
commit: "test: probe hooks that record what the harness really does"
---

## Why

Several features the design leans on are unconfirmed (`context.md`, "Not verified yet"). Building a stage on a
feature that does not exist, or behaves differently on this harness, costs the whole stage. This task turns
each assumption into a recorded fact before any check is written. Every stage after it re-plans on its results.

## What to build

A probe plugin under `tools/probes/`, never shipped, loaded with `claude --plugin-dir`. Each hook writes what it
received and what happened to a JSONL file. Probe these on Windows:

1. **PreToolUse Bash returning `updatedInput` with `allow`.** Does the rewritten command run? Does the result the
   model sees show the rewritten command or the original?
2. **PreToolUse Write returning `updatedInput`** whose `content` holds `\r\n` and a U+FEFF at the start. Are the
   bytes on disk exact?
3. **PreToolUse Edit returning `updatedInput`** with `old_string` and `new_string` both extended by one
   character on the right. This is the ANC-4 fix in task 17.
4. **PostToolUse on Read returning `additionalContext`.** Does the model see it? Ask it in the session.
5. **PostToolUseFailure on Edit:** the payload fields, the error text, and whether `additionalContext` reaches
   the model.
6. **PostToolUse on Bash:** is `bashEditDiff` present, and does it need `bashEditDiffEnabled: true` in user
   settings?
7. **SessionStart:** does `CLAUDE_ENV_FILE` exist, and do variables written to it reach later Bash calls?
8. **PostToolUse `updatedToolOutput` and `classifierContext`:** accepted, ignored, or refused?
9. **Exec form against shell form** (`command` with and without `args`) for starting Python. Record the time each
   takes.
10. **Failure modes:** a hook that crashes, one that runs past its `timeout`, one that prints invalid JSON. What
    does the session see, and does the tool call still run?
11. **The desktop Code tab:** does it load a plugin installed from a local marketplace? It cannot take
    `--plugin-dir`, so use `claude plugin marketplace add <clone path>`.
12. **`mcp_tool` hooks, the gate for the one-process runtime (D13).** Can a hook of type `mcp_tool` hand the event
    to a tool on the plugin's own MCP server, and does the tool's answer act as the hook's decision? The docs
    promise string `${path}` substitution in `input` and nothing more. Record what an absent field, a boolean and an
    object become (`${tool_input.replace_all}`, `${tool_input.content}`), and whether a hook-invoked MCP tool
    prompts the user. Measure its latency against a command hook.
13. **`ask` with `updatedInput`:** does the user see the rewritten command in the prompt?
14. **A hook `allow` in auto mode:** does the auto-mode classifier still judge the call, or does the `allow` skip
    it (D12)?
15. **The MCP client:** with a probe stdio server that logs every request, record which era Claude Code uses (the
    legacy `initialize` or the modern `server/discover` and `_meta`). Check the desktop app and the CLI, with and
    without `MCP_PROTOCOL_NEGOTIATION=auto`, and record `MCP_SDK_GENERATION`.
16. **MCP features in Claude Code:** does it answer `resultType: "input_required"` with an elicitation form, and
    the legacy `elicitation/create`? Does it render an MCP App (`_meta.ui.resourceUri`) in the desktop Code tab or
    in Cowork? Does it declare the Tasks extension, or show progress notifications?
17. **Prompts on MCP tools:** do `io.*` calls prompt in manual mode, and does `readOnlyHint` or `destructiveHint`
    change the prompt?
18. **A dead server:** kill the probe server mid-session. What does the next `mcp_tool` hook show, and does the
    tool call run?

## Where

`tools/probes/`. Results go into `.claude/tasks/context.md`: each confirmed item moves from "Not verified yet" to
"Doc facts" or "Verified live", with the Claude Code version and the surface that ran it. Task 04 turns them into
`docs/compat.md` and `docs/live-checks.md`.

## Done when

- Every item above has a recorded result on Windows.
- Item 12's result is written into `docs/design/architecture.md`, section 6. If the substitution fails, the command
  hooks through `hook.sh` become the primary runtime, and that section says so.
- Tasks 06 to 27 are updated wherever a result changes their approach.

## Notes

- The lead's machine runs Claude Code desktop with bundled 2.1.281 and a separate CLI at 2.1.283. The desktop
  app is the lead's main surface, so every probe runs there first.
- The macOS probes wait in task 36 (D21): the Bash tool with a 9 KB command and `echo 'a\\b' | od -c`, and
  `bash --version` through the Bash tool.
