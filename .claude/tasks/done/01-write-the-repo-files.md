---
title: Write the git attributes, the ignore list and the editor config
stage: A
area: infra
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: []
findings: [BYT-1, BYT-2, SHW-1]
platforms: [windows, macos]
commit: "chore: git attributes, ignore list and editor config"
---

## Why

The byte fixtures need protecting. With `core.autocrlf=true`, a CRLF fixture committed as text comes back
converted, and every byte test after that tests the wrong bytes. Both platforms also need to check out the same
bytes of the product code.

## What to build

- **`.gitattributes`:** `* text=auto eol=lf` for the product code, so both platforms check out the same bytes.
  `tests/fixtures/** -text`, so byte fixtures keep CRLF, BOMs and invalid UTF-8 exactly.
- **`.gitignore`:** `__pycache__/`, `*.pyc`, `.venv/`, `corpus/` and exported telemetry, above the block the kit's
  `install.ps1` manages. Never edit inside that block: the installer rewrites it, and it keeps the kit's links out
  of git (D11).
- **`.editorconfig`:** UTF-8, LF, 4 spaces for Python, `max_line_length = 110` (D17), trailing whitespace trimmed
  except in Markdown.

## Where

`.gitattributes`, `.gitignore` and `.editorconfig` at the repo root.

## Done when

- `git check-attr -a tests/fixtures/<any>` reports the fixture as not text.
- A CRLF fixture committed, removed and checked out again is byte-identical (`cmp`) on Windows. Task 05's fixture
  self-check proves the same on the macOS runner.
- `install.ps1 -ProjectPath <this clone>` from the kit reports every link as linked, and its gitignore block is
  unchanged.

## Notes

- `CLAUDE.md`, `.claude/rules/` and `.claude/skills/` were settled in the handover (task 00, in `done/`).
- The Python floor (3.14, D15) and the line length (110, D17) are decided.

## What changed

- **`.gitattributes`:** `* text=auto eol=lf`, then `tests/fixtures/** -text`.
- **`.gitignore`:** `__pycache__/`, `*.pyc`, `.venv/`, `/corpus/`, `/events/` and `/reports/`, above the kit's block.
  The lead chose `/events/` and `/reports/` for exported telemetry (D22).
- **`.editorconfig`:** UTF-8, LF, a final newline and trimmed trailing whitespace for every file, 4 spaces and
  `max_line_length = 110` for Python, no trimming in Markdown. `[tests/fixtures/**]` unsets all four byte settings,
  so an editor never converts a fixture on save. The lead approved that section.
- **Docs:** `context.md` gained D22 and the git attributes facts. `.claude/tasks/README.md` and the `io-guard-dev`
  skill now say D1 to D22. The drawing, `architecture.md`, `README.md`, `CLAUDE.md` and the compatibility pages
  needed nothing: no component, contract, feature, harness fact or layout changed.

Evidence:

- `git check-attr -a tests/fixtures/crlf.txt` and `tests/fixtures/sub/bom.cpp` report `text: unset`.
  `plugins/io-guard/scripts/hook.py` and `README.md` report `text: auto` and `eol: lf`.
- Five probes were staged in `tests/fixtures/`: CRLF, BOM with CRLF, cp1250, lone CR and mixed. Each matched its
  written bytes in the index blob, through `git cat-file --filters`, and after a delete and `git checkout-index`.
  The same five probes in a control folder came back LF, except the lone-CR one, which git classes as not text.
  The probes were unstaged and deleted, and the index holds only `LICENSE` again.
- `git check-ignore` matches all seven sample paths the new lines cover, and none of
  `tests/mcp/requests/legacy.jsonl`, `plugins/io-guard/ui/dashboard.html`, `tools/report.py` or
  `docs/architecture.svg`.
- The kit's installer report, before and after: linked 6, absent 0, to repoint 0, extra 0. The block it manages
  is 379 bytes with sha256 `391cc817dec0ca1caabf324d887e9fb59d2e20f17f4417626385d48255da9e2a` before and after.
- `git status -uall` lists none of the kit's links.

Checked on Windows 10 with Git for Windows 2.49.0 and `core.autocrlf=true` on 2026-09-27. No Claude Code live check
was needed.

Not checked:

- **macOS.** Task 05's fixture self-check proves the round trip on the macOS runner.
- **A real installer write.** The run was the report only. `Update-GitIgnore` in the kit's `install.ps1` keeps
  every line above its block and writes the block after one blank line, which is the shape the file has now.
- **The working copies of `LICENSE` and `.gitignore` are still CRLF.** `core.autocrlf` wrote the first and the
  installer wrote the second. `LICENSE` is LF in the index, `.gitignore` goes in as LF when it is staged, and a
  fresh checkout gives LF.

Commit subject, approved by the lead: `chore: git attributes, ignore list and editor config`.
