# This repository

- **Read `.claude/tasks/README.md`, `.claude/tasks/context.md` and `docs/design/architecture.md` before the first
  task.** The `io-guard-dev` skill says how code here is written, tested and verified.
- **Shipped code is Python standard library only, Python 3.14 or later** (D4, D15). Claude Code installs no Python
  packages for a plugin.
- **One codebase for Windows and macOS.** Never hard-code a path separator, a shell or an interpreter name. The
  platform is detected at run time.
- **The lead's Mac is down** (D21). Live checks run on Windows, CI runs both platforms, and every macOS live check
  waits in task 36.
- **The plugin ships only `plugins/io-guard/`.** It has no top-level `bin/`, and its manifest paths use forward
  slashes.
- **io-guard is for anyone's projects, not only the lead's Unreal ones.** Nothing it ships or tells a model names
  Unreal, the lead's kit, its tools such as `bridge.py`, or the lead's projects, in code, a message, a default or
  an example. A project's own advice belongs in that project's skills. The lead set this on 2026-09-27.
- **Transcripts, the replay corpus, telemetry and anything copied from them stay on the machine and out of git**
  (D8). They hold the lead's paths and project content.
- **`workbench/` holds byte-exact copies of the lead's project files to test on.** `workbench/MANIFEST.sha256`
  holds each copy's hash as it left the source project. It stays on the machine and out of git, like the corpus.
- **The kit's skills, rules and tools arrive through gitignored links** (D11). Git writes through a tracked link
  into the kit, so a link is never added to git, not even with `-f`.
- **Before any push that makes content public, task 34's scrub runs first.**
