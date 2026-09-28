---
title: Let a project's list only add to a list that makes io-guard stricter
stage: I
area: config
created: 2026-09-28
status: open
depends-on: [18, 29]
findings: []
platforms: [windows, macos]
commit: "fix: a project's list adds to the user's where a longer list is stricter"
---

## Why

A project file restricts and never widens (`docs/design/architecture.md`, section 5, and `lib/config.py`). The
config merge replaces a list, though, and only a key ending in `extra` appends. So a project's
`.claude/io-guard.json` that sets `checks.verify.write.ascii_only` to `[".md"]` drops a `.py` the user listed,
and a project that sets it to `[]` turns the check off for that project. The lead found this on 2026-09-28,
while asking how CLICKER could keep `.py` and `.md` ASCII.

## What to build

- Mark each list key where a longer list is stricter, so a project's list joins the user's instead of
  replacing it. `ascii_only` is one. Go through the others and decide each, stating the reason in the key:
  - stricter when longer, so a project adds: `ascii_only`, and likely `win.paths` `prefixes`
  - looser when longer, where a project adding is a choice the README already grants: `invisible_allowed`,
    `skip_trees`, `noise_patterns`
  - lists that describe the machine or the tools, such as `build_commands`, `readers`, `builds`, `runs` and
    `code_pages`, where replacing is the point
  - `commit_policy.forbid`, which a project may not set at all
- Test a project list that adds to, and one that tries to shrink, a user list, for each key marked.
- Let `ascii_only` name a whole file name as well as an extension. It matches `path.suffix`, which is empty
  for `pyrun`, `LICENSE`, `.gitignore`, `.gitattributes` and `.editorconfig`, so this repository's own list,
  set on 2026-09-28 when the lead asked for ASCII in everything written here, cannot reach them.
- Say in the README which lists a project adds to.

## Where

`plugins/io-guard/scripts/ioguard/lib/config.py`, the `ConfigKey` declarations in `checks/`,
`tests/lib/test_config.py`, `README.md`, `docs/design/architecture.md` section 5.

## Done when

- A project cannot drop an extension from the user's `ascii_only`, and each list key states which way it merges.
