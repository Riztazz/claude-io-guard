---
title: Verify the hook and MCP features the design relies on
stage: A
area: runtime
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
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

## What changed

- **`tools/probes/`**, never shipped. `run_probe.py` builds a one-off plugin per probe from `plugin/scripts/`:
  a command hook (`probe_hook.py`), a stdio MCP server that answers both eras (`probe_server.py`), and the
  answer each mode gives (`answers.py`). It runs `claude -p` with the plugin, times each hook from the stream,
  and writes every log to `workbench/probes/`, which git ignores. `list`, `run`, `brief`, `timing`, `show` and
  `assemble` are its commands. 29 probes cover the 18 items.
- **Every item has a result on Windows**, in `context.md`, "Hooks and MCP", one row per item. Item 11 came
  from task 02 and the io-probe install. Items 13 and 16 on the desktop were run in a Code tab session with the
  lead watching: the permission prompt showed the rewritten command, and no form appeared.
- **Item 12 passed**, so the one-process runtime stands (D13). `docs/design/architecture.md`, section 6, records
  the substitution rules, the latency and the fail-open behaviour. Sections 2 and 6 now pass `tool_input` and
  `tool_response` whole as `${tool_input}` and `${tool_response}` JSON text, because a flat map of strings cannot
  tell an empty `new_string` from an absent one. Section 6 states the `updatedToolOutput` shape. Section 7 no
  longer relies on elicitation, which no probed surface shows the user, and asks through a hook `ask` instead.
- **Results that change later tasks:**
  - 06: `mcp_tool` is the primary path, and the three timings are the expected order.
  - 08: the bridge decodes `${tool_input}` and must check `${tool_response}` and a large Write live.
  - 20: an Edit whose anchor is missing fires no hook after the call, so the Edit branches move to
    PreToolUse. A stale view no longer fails the Edit.
  - 21: `bashEditDiff`'s real shape, and the missing "modified since read" failure.
  - 22: `updatedToolOutput` takes the tool's own output object.
  - 23: the modern client's strict results, the server restart, and no reliance on elicitation. Its claim that
    Claude Code never reconnects a stdio server was wrong and is gone.
  - 25: an ask rule goes through a hook `ask` on the `io.run` call.
  - 33: neither the desktop Code tab nor the CLI renders an MCP App.
- **Docs:** `context.md` (the results, and a shorter "Not verified yet"), `docs/design/architecture.md`
  (sections 1, 2, 6 and 7), `CLAUDE.md` (the layout), and the task files above. The drawing needed nothing,
  because it already shows the `mcp_tool` path. `README.md` needed nothing either: its settings snippet already
  sets `bashEditDiffEnabled`. `docs/compat.md` and `docs/live-checks.md` do not exist yet. Task 04 builds them
  from these rows.

Checked on Windows 10 on 2026-09-27: `claude` CLI 2.1.283, and the desktop app's Code tab on its bundled 2.1.281.

Not checked:

- **macOS.** Every item waits in task 36 (D21).
- **The desktop's manual-mode prompt on an MCP tool** (item 17). The desktop session that ran the probes was in
  auto mode, so only the CLI result stands.
- **The desktop's notice when the server cannot start** (item 18). The stream reports the hook error, and nobody
  looked at the desktop.
- **Cowork**, for Apps and elicitation.
- **A `${tool_input}` substitution larger than a three-line Write**, and `${tool_response}`. Task 08 checks both.
- **The probe runs load the lead's own plugins and user CLAUDE.md.** Sonnet refused the first auto-mode command,
  a force-push, citing the lead's rule that every push needs a grant. The probe moved to deleting a scratch
  folder.

The probe plugin io-probe was installed for the desktop check and removed afterwards with
`claude plugin marketplace remove io-probe-local`. `claude plugin list` shows no io-probe row.

Commit subject: `test: probe hooks that record what the harness really does`.
