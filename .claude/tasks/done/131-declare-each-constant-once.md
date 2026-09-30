---
title: Declare each shared constant and small helper once
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: one declaration for each shared constant"
---

## Why

Medium. Several constants and two-line helpers are declared twice or more, in files that never read each
other's copy, so a change to one leaves the other behind.

- The private-use regex is the same text in two modules:
  `plugins/io-guard/scripts/ioguard/lib/profile.py:22` and `plugins/io-guard/scripts/ioguard/lib/text.py:14`,
  both `PRIVATE_USE = re.compile(f"[{chr(0xE000)}-{chr(0xF8FF)}{chr(0xF0000)}-{chr(0x10FFFD)}]")`.
- `plugins/io-guard/scripts/ioguard/lib/output.py:26-27` builds a character class by hand,
  `"".join(f"{chr(low)}-{chr(high)}" for low, high in CODE_PAGE_SPANS)`, where
  `plugins/io-guard/scripts/ioguard/lib/text.py:25-27` has `character_class`, which also escapes each end.
- `profile.BOM_CHAR` (`lib/profile.py:253`) exists, and `chr(0xFEFF)` is spelled again at
  `lib/editorconfig.py:21`, `lib/text.py:15`, `lib/text.py:37`, `lib/text.py:38`,
  `checks/conform_write.py:104`, `checks/conform_edit.py:56` and `checks/diagnose.py:72`.
- `POWERSHELLS = frozenset({"powershell", "pwsh"})` is declared at `checks/lint.py:26` and again at
  `lib/rules.py:44`.
- `lib/shell.py:511` names `TAKES_VALUE = {"-W", "-X"}`, and `lib/shell.py:549` spells the same pair as a
  literal, `if word in ("-W", "-X")`, in the function beside it.
- The file "as the Edit tool reads it" is computed three ways: `anchors.edit_view` (`lib/anchors.py:38-40`),
  `LINE_BREAK.sub("\n", part)` in `lib/drift.py:73`, and `drift.text_of` plus `edit_view` plus a BOM strip in
  `checks/diagnose.py:70-72` and `checks/conform_edit.py:56`.
- This Python's `ToolVersion` is built twice: `Probe.unprobed` at `lib/context.py:104` without a stamp, and
  `probing.this_python` at `lib/probing.py:55-57` with one.
- `Tool.named` (`lib/events.py:39-41`) and `PermissionMode.named` (`lib/events.py:54-55`) are the same body,
  an enum member by value with a fallback member, and `events.member` (`lib/events.py:75-79`) is a third
  variant that raises.

The engineering skill's rule is one declaration per fact. Each pair above is a place where the two copies
drift on the next change, and nothing tests that they agree.

## What to build

- `text.PRIVATE_USE` is the one regex, and `profile` imports it, or the ranges live in `text` and both build
  from them.
- `output.CODE_PAGE_RUN` builds through `text.character_class`.
- Every `chr(0xFEFF)` outside `profile.py` becomes `BOM_CHAR`.
- One `POWERSHELLS`, in `lib/rules.py` or `lib/shell.py`, which `lint` imports.
- `python_reads_stdin` reads `TAKES_VALUE`.
- One function gives text as the Edit tool reads it, BOM off and every ending as LF, and `drift`, `diagnose`
  and `conform_edit` call it.
- `Probe.unprobed` calls `probing.this_python`, or `probing` is the one home for it.
- One generic "member by value, or this fallback" helper in `lib/events.py`, which both enums call.

## Where

`lib/profile.py`, `lib/text.py`, `lib/output.py`, `lib/editorconfig.py`, `lib/shell.py`, `lib/drift.py`,
`lib/anchors.py`, `lib/context.py`, `lib/probing.py`, `lib/events.py`, `lib/rules.py`, `checks/lint.py`,
`checks/conform_write.py`, `checks/conform_edit.py`, `checks/diagnose.py`.

## Done when

- A grep of `plugins/io-guard/scripts` finds one `PRIVATE_USE`, one `POWERSHELLS`, and `chr(0xFEFF)` only in
  `profile.py`.
- The suite passes.

## What changed

Validated on 2026-09-30 before building: every pair was there. Two corrections: task 129 moved
`checks/diagnose.py:72` to `lib/diagnosis.py:65`, and a `chr(0xFEFF)` the task did not list sat in
`cli/labels.py:39`. The done-when put the one `chr(0xFEFF)` in `profile.py`, but `profile` needs
`text.PRIVATE_USE` and `text` needs the BOM character, and one of the two has to import the other. `text`
imports nothing from io-guard, so it holds both, and `profile` imports them.

- `lib/text.py` declares `BOM_CHAR`, `PRIVATE_RANGES` and `PRIVATE_USE`, built through `character_class`, and
  `INVISIBLE_RANGES` takes `PRIVATE_RANGES`. `profile`, `drift`, `code_tokens`, `editorconfig`,
  `conform_write`, `mcp.in_place` and `cli.labels` take `BOM_CHAR` from there.
- `output.CODE_PAGE_RUN` builds through `text.character_class`. Both rebuilt patterns have the same text as
  HEAD's, compared directly.
- `lib/rules.py` holds the one `POWERSHELLS`, which `checks/lint.py` imports.
- `python_reads_stdin` in `lib/shell.py` reads `TAKES_VALUE`.
- `anchors.file_view` is a whole file as the Edit tool reads it: no BOM, then `edit_view`. `drift.edited`,
  `diagnosis.file_text` and `conform_edit` call it. `edit_view` itself keeps a leading U+FEFF, since it also
  reads old_string and new_string, where the character is text.
- `ToolVersion.this_python` and `file_stamp` moved from `lib/probing.py` to `lib/context.py`, beside
  `ToolVersion`, since `probing` imports `context` and not the other way. `Probe.unprobed` calls it, so the
  fallback probe's Python now carries its stamp as the measured one does.
- `events.by_value(enum, value, fallback)` is the lookup both `Tool.named` and `PermissionMode.named` call.
  `events.member`, which raises, stays: an unknown hook event is an error, and an unknown tool is not.

`tests/test_declarations.py`, 8 tests: one `chr(0xFEFF)`, one declaration each of `PRIVATE_USE`,
`POWERSHELLS`, `PROGRAM_SUFFIXES` and `BOM_CHAR`, the readers sharing one object, one character class
builder, one spelling of `-W` and `-X`, one file view, one Python version, and one enum lookup. All 8 failed
first, each on a missing helper or a second copy. `tests/lib/test_probing.py` imports `file_stamp` and
`ToolVersion.this_python` from their new home.

Docs: `docs/design/architecture.md` section 1, the tree's lines for `anchors`, `events`, `context` and
`text`, and section 4's `anchors` block, which lists `file_view`.

Evidence, on Windows on 2026-09-30:

- The suite: 1,076 tests, 1,068 before, OK with 2 skipped.
- A replay over the corpus with HEAD's code and with this change: 7 checks, 0 differences.
- The rebuilt `PRIVATE_USE` and `CODE_PAGE_RUN` have the same pattern text as HEAD's, so every code point
  matches as before.
- Live, Claude Code 2.1.283, from this checkout: `live-conform`, `live-diagnose`, `live-read-profile`,
  `live-invisible` and `live-results` pass. `live-space-dropped` read FAIL without reaching the changed code:
  the probe's work folder takes this repository's own `.claude/io-guard.json`, where the lead turned
  conform.edit off on 2026-09-29. The probe's own Edit, run offline through the pipeline, is refused with
  SPACE_DROPPED by HEAD's code and by this change alike. So conform.edit's use of `file_view` is checked by
  the suite and that offline run, not live. Filed as task 146.
