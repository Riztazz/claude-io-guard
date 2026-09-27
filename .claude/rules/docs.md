# Keeping the docs current

- **A change updates every doc it makes wrong, in the same change.** A doc that describes last week's plugin
  misleads the next agent and every reader of the public repository, and no test catches it.
- **Which doc a change makes wrong:**

| Doc | Update it when a change |
|---|---|
| `docs/architecture.svg` | adds, removes or renames a component, changes how a call flows, or changes a default the drawing states: the rewrite modes, the 300 ms and 2 s budget, fail-open, the server-down warning |
| `docs/design/architecture.md` | changes a signature, a type, a code, a config key, a thread, a file in the plugin data folder, or the package layout |
| `README.md` | changes what the plugin fixes, an io tool, a requirement, an install step, a default or a setting |
| `docs/compat.md`, `docs/live-checks.md` | runs a live check, or starts relying on a harness feature |
| `.claude/tasks/context.md` | makes a decision or verifies a fact |
| `CLAUDE.md` | changes the repository's layout or how to run something |

- **In the drawing, one fact has several copies, and they change together:** the box and its hover text in `<title>`,
  the arrow and its badge, and the step text in the script's `STEPS`. GitHub shows only the boxes, the arrows and the
  badges, so the static picture has to be right on its own. The README links the interactive copy, which GitHub Pages
  serves from `docs/` on `main` after each push.
- **Check the drawing after every edit.** It parses as well-formed XML, for example with Python's
  `xml.dom.minidom`, and it is ASCII. Then serve `docs/` on localhost with `python -m http.server` and open
  `architecture.svg` there: the browser pane shows a local file only as a static snapshot. Pick each flow, press
  Play, and hover a box.
- **A task's `## What changed` names each doc it updated**, or says that none needed it.
