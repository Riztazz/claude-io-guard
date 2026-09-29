---
title: Answer a dropped settings page request without a traceback
stage: I
area: mcp
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: the settings page lets a closed connection go quietly"
---

## Why

Found in task 120 on 2026-09-29. Each full test run on Windows prints two tracebacks from the settings page
server, from `tests/mcp/test_tools_dashboard.py`'s test of a body with no length, a negative one or one too
long. The client closes its connection before the server answers 400, and `dashboard_http.py` `answer`
raises out of `self.wfile.write(body)`:

```
  File "...\ioguard\mcp\dashboard_http.py", line 182, in do_POST
    self.json(400, {"message": "A change names its length, at most 64 KB."})
  File "...\ioguard\mcp\dashboard_http.py", line 141, in answer
    self.wfile.write(body)
ConnectionResetError: [WinError 10054] An existing connection was forcibly closed by the remote host
```

The tests pass. A page closed in the middle of a request, in real use, prints the same traceback into the io
server's log, where it reads like a failure.

## What to build

- `answer` lets `ConnectionError` go, as `BrokenPipeError` and `ConnectionResetError` are, since a client
  that left needs no answer. It logs one debug line instead.
- A test that closes a connection before the answer and finds no traceback on the server's error stream.

## Where

`mcp/dashboard_http.py` (`answer`), `tests/mcp/test_tools_dashboard.py`.

## Done when

- A full test run prints no traceback, and the test passes.
