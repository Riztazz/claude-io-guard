---
title: Link the kit's generic rules and skills instead of keeping copies
stage: A
area: docs
created: 2026-09-27
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "docs: link the kit's generic rules and skills, and keep io-guard's own"
---

## Why

The lead decided on 2026-09-27 that the Unreal kit (UNREAL-SHARED) owns every rule and skill (D11). This
repository held seed copies of them, written on 2026-09-27, whose opening lines named the Unreal skills they came
from. It was task 33 before the renumbering.

## What to build

- Hand the seeds to the kit's new generic group, and link that group in here with the kit's `generic` profile.
- Keep what belongs to this repository alone: `.claude/rules/this-repo.md` and `CLAUDE.md`.
- Keep the links out of git.

## Where

This repository's `.claude/`, `.gitignore` and `CLAUDE.md`, and the kit.

## Done when

- A session here loads the generic rules and skills through the kit's links.
- No rule or skill file exists both here and in the kit.

## What changed

Done on 2026-09-27 during the handover, on Windows.

- **The kit** gained the `generic` profile, and `install.ps1 -ProjectPath <this clone> -Profile generic` linked
  `.claude/rules/shared`, `.claude/skills/engineering`, `prose`, `testing` and `verification`, and
  `.claude/tools/shared`. It wrote the kit's two hooks and the compaction window into `.claude/settings.local.json`,
  and its managed block in `.gitignore` lists every link.
- **The links stay out of git (D11).** A scratch test showed git writing through a tracked junction into the kit
  (`context.md`, "Git through a junction"). `git status` here shows none of the linked files.
- **The seeds are gone:** the six generic rule files, the `engineering`, `testing`, `verification` and `prose`
  copies, `python-standards`, and `rules-map.md`, which moved to the kit as `rules/README.md`. Their general rules
  live in the kit, cleaned of the Unreal lineage.
- **This repository's own rules** are `.claude/rules/this-repo.md` and the new `io-guard-dev` skill, which holds
  the layout, the Python rules, the tests, replay and the live checks for io-guard.
- **`CLAUDE.md`** names the links, what they carry, and that they are never edited or tracked here.

**Checked on Windows on 2026-09-27:** the installer's report showed the six links as linked, `git status` listed
only this repository's own files, and the kit hooks' `after-compact.py` printed the no-editor step here.

**Not checked:** a live session here loading `.claude/rules/shared` through the junction. The CLI's OAuth session
had expired. The Mac is down (D21).

**Proposed commit subject:** `docs: link the kit's generic rules and skills, and keep io-guard's own`
