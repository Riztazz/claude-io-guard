---
title: Let a project's list only add to a list that makes io-guard stricter
stage: I
area: config
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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

## What changed

- `lib/config.py`: `ConfigKey.project_joins`, and `joined`. In a project layer, a list for a key so marked is
  added after the list below it, with no entry dropped and none repeated. The user's own layer still replaces.
- The keys, decided one by one:
  - adds, since a longer list is stricter: `checks.verify.write.ascii_only`, `checks.win.paths.prefixes`
  - replaces, since a longer list is looser and the README grants a project these: `noise_patterns`,
    `skip_trees`, `invisible_allowed`
  - replaces, since they describe the project's tools: `build_commands`, `readers`, `builds`, `runs`,
    `code_pages`, `posix_roots`, `msys_programs`. `posix_roots` is kept here, as a list of what Git Bash does,
    though a longer one catches more.
  - `commit_policy.forbid` stays a key a project may not set.
  Each list key's text ends by saying which, and `test_every_list_key_says_how_a_project_list_merges` holds it.
- `checks/verify_write.py`: `ascii_kept(path, names)`, true for a listed extension or a listed whole file name,
  without regard to case. `cli/precommit.py` uses it too, where it had its own copy of the extension test.
- `.claude/io-guard.json`: this repository's `ascii_only` adds `pyrun`, `LICENSE`, `.gitignore`,
  `.gitattributes` and `.editorconfig`.
- Tests: `tests/lib/test_config.py` (3: adds, shrinks and repeats against the user's list, the user may still
  shorten it, every list key says its merge) and `tests/checks/test_verify_write.py` (1, whole names).
- `tools/probes/run_probe.py`: `live-ascii-joined`.
- Docs: `README.md` (Configure it), `docs/design/architecture.md` (the config layers), `docs/live-checks.md`,
  `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 853 tests, all passing, up from 849. The join test fails under the old merge,
  where a project's `[]` replaced the user's list.
- `live-ascii-joined` passed on 2.1.281 and 2.1.283: with the user's `ascii_only` of `.py` and the project's of
  `[]`, a Write of a non-ASCII `.py` got `NON_ASCII_ADDED`.
- Checked on Windows on 2026-09-28.
