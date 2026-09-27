---
title: Scaffold the plugin and its marketplace
stage: A
area: infra
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [01]
findings: []
platforms: [windows, macos]
commit: "feat: the io-guard plugin skeleton and its marketplace"
---

## Why

Every later task adds a component to this skeleton. The repository is both the marketplace and the plugin (D1 in
`context.md`). Claude Code copies only the plugin's own directory into a user's cache, so the shipped plugin
lives in a folder of its own, and the tests, tools and task notes beside it never ship.

## What to build

```
.claude-plugin/marketplace.json          the catalog: one entry, io-guard, source ./plugins/io-guard
plugins/io-guard/.claude-plugin/plugin.json
plugins/io-guard/skills/io-guard/SKILL.md   a stub, filled in task 27
plugins/io-guard/scripts/                    Python code, never bin/
```

- `marketplace.json`: `name` `claude-io-guard`, `owner`, and one entry named `io-guard`. The entry name and the
  manifest name stay equal, or installs by the manifest name fail.
- `plugin.json`: `name` `io-guard`, description, author, `homepage` and `repository`
  `https://github.com/Riztazz/claude-io-guard`, license MIT. No `version`, so installs track commits until 1.0
  (D18). `userConfig.python`, titled "Python interpreter", default `python3`, described as "The command that starts
  Python 3.14 or later. Windows with python.org Python: python" (D15).
- No hooks yet. Task 06 adds the first one.
- `README.md` exists from the handover. Correct its install lines if a name here changes.

## Where

The paths above.

## Done when

- `claude plugin validate .` and `claude plugin validate plugins/io-guard` pass on Windows.
- On this machine, `claude plugin marketplace add <path to this clone>` and
  `claude plugin install io-guard@claude-io-guard` succeed, and `claude plugin list` shows it enabled. Remove
  it again afterwards with `claude plugin marketplace remove claude-io-guard`.
- The desktop app's Code tab, the lead's main surface, shows the plugin installed from the local marketplace. It
  cannot take `--plugin-dir`.
- `claude --plugin-dir plugins/io-guard` loads the stub skill.

## Notes

- The `claude` CLI on this machine is 2.1.283 and the desktop app bundles 2.1.281. The plugin needs 2.1.281 for
  `mcp_tool` hooks that wait for their server (`docs/design/architecture.md`, section 13).
- A top-level `bin/` makes Chat and Cowork refuse the whole plugin, and plugin `bin/` directories once ate the
  Windows command budget (#95653). Scripts go in `scripts/`.
- Component paths use forward slashes. A backslash path fails on macOS.

## What changed

- **`.claude-plugin/marketplace.json`:** `claude-io-guard`, owner Riztazz, one entry `io-guard` with source
  `./plugins/io-guard`.
- **`plugins/io-guard/.claude-plugin/plugin.json`:** name, description, author, `homepage`, `repository`, MIT, no
  `version` (D18), and `userConfig.python` with the title, description and default the task names (D15). The
  author and the owner carry a name and a GitHub URL, and no email, because the repository is public.
- **`plugins/io-guard/skills/io-guard/SKILL.md`:** the stub. Its description already names the trigger task 27
  keeps: an io-guard code in a tool result.
- **No `scripts/` folder yet.** Git keeps no empty folder, and task 06 writes the first file there.
- **Docs:** `context.md` gained the live results below, a doc fact on where `${user_config.KEY}` is substituted,
  and a new open question for task 06: whether `${user_config.python}` falls back to its default. `CLAUDE.md` says
  which files exist today. `README.md` needed nothing, because its install lines already use these names. The
  drawing and `architecture.md` needed nothing either, because section 1 already names these files.

Evidence, `claude` CLI 2.1.283:

- `claude plugin validate .` and `claude plugin validate plugins/io-guard` exit 0 with "Validation passed with
  warnings". Each has one warning, "No version specified", which D18 intends. `--strict` exits 1 on both, so task
  05's CI runs `validate` without it.
- `claude plugin marketplace add <this clone>` and `claude plugin install io-guard@claude-io-guard` succeeded.
  `claude plugin list` showed `io-guard@claude-io-guard`, `Status: enabled`, `Version: 87246a2a7012`.
  `claude plugin details io-guard` showed Skills (1) `io-guard`, about 109 tokens in every session.
- **The desktop app's Code tab** listed `/io-guard:io-guard` in a new session while the plugin was installed. The
  lead checked it. The app's folder holds Claude Code 2.1.280 and 2.1.281, and the version that session ran was
  not recorded.
- `claude plugin marketplace remove claude-io-guard` removed the marketplace and uninstalled the plugin.
  `claude plugin list` then showed no io-guard row.
- `claude -p --plugin-dir plugins/io-guard` listed `io-guard:io-guard` with its description, after the install
  was gone.

Checked on Windows 10 on 2026-09-27.

Not checked:

- **macOS.** CI on the macOS runner validates the manifests from task 05 on. A live install waits in task 36.
- **`~/.claude/settings.json` is not byte-identical to before.** The removal left `"enabledPlugins": {}` and
  `"extraKnownMarketplaces": {}` and added a final newline: 245 bytes against 188. Both keys are empty, so no
  setting differs. `known_marketplaces.json` is byte-identical.

Commit subject, approved by the lead: `feat: the io-guard plugin skeleton and its marketplace`.
