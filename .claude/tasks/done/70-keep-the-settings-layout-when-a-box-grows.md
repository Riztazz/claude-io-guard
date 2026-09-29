---
title: Keep the settings page's layout when a box grows, and make the boxes a little bigger
stage: I
area: ui
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [33]
findings: []
platforms: [windows, macos]
commit: "fix: a list or JSON box on the settings page sits under its name, and grows only down"
---

## Why

On 2026-09-29 the lead resized the JSON box of the Verify setting, and the page's layout broke: the box sat in
the same row as the option's name, so a wider box pushed the name into the middle of the card and the Save
button out beside it. The lead also asked for the boxes to be a bit wider and a bit taller by default.

## What changed

- `ui/dashboard.html`: a list or a JSON setting puts its control on its own line under the name, at the card's
  full width, for yours and for the project's override. The JSON box grows only downward, with Save under it.
  Text and number boxes take 7 by 10 pixels of padding and 34 pixels of height, the number box is 10 characters
  wide and the text box 16, and the JSON box starts at 110 pixels.
- No test change: `tests/mcp/test_tools_dashboard.py` still holds the page ASCII and self-contained.

Evidence:

- The page, served from this checkout over copies of the lead's config, at a 1000-pixel viewport: the Verify
  card's name stayed at its left edge with the box under it, 759 of the card's 788 pixels wide, and Save stayed
  under the box when the box grew from 260 to 400 pixels. `resize` is `vertical`. A number box measured 140 by
  36, a text box 224 by 36, and the build commands' chips sat under the name row at 759 pixels.
- `python tests/run_all.py` from Git Bash ran 893 tests, all passing.
- Not seen as a screenshot: the pane did not draw while the app sat behind another window, so the layout was
  measured through the page instead.
