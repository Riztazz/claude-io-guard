---
title: Declare each shared constant and small helper once
stage: I
area: runtime
created: 2026-09-29
status: open
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
