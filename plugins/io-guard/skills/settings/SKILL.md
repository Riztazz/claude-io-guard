---
name: settings
description: Opens io-guard's settings page, where each check turns on or off, each rewrite mode and list changes, and a project overrides any of them. Use it when the user asks to see or change io-guard's settings, or picks it from the plugin menu.
---

# Open io-guard's settings page

1. Call `mcp__plugin_io-guard_io__io_dashboard` with no arguments. When only its name is listed, load it first
   with ToolSearch and the query `select:mcp__plugin_io-guard_io__io_dashboard`.
2. Open the `url` it returns for the user in the desktop app's browser pane, where one is available.
3. Give the user the whole `url`, token and all, as a Markdown link whose text is the URL itself, such as
   `[http://127.0.0.1:PORT/?token=TOKEN](http://127.0.0.1:PORT/?token=TOKEN)`. A click opens the page in their
   own browser on this machine.
4. Tell the user, in two lines, which checks the result says are off for this project, and that the page stops
   a few minutes after it closes.

The page writes through `io.config`, so a change applies from the next tool call. To change one setting
without the page, call `mcp__plugin_io-guard_io__io_config` with the key and the value instead.
