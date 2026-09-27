"""io-guard's command-hook entry point: python hook.py <event>, with the hook event as JSON on stdin.

It answers with at most one ASCII JSON object on stdout and exits 0. On session_start it checks that this
Python and the interpreter the io server starts from are both 3.14 or later, and warns once when either is
not. Every event writes one line to the session's file under ${CLAUDE_PLUGIN_DATA}/events/. Task 08 puts the
check pipeline behind it.

This file runs on older Pythons long enough to say that they are too old, so it avoids syntax newer than 3.8.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MINIMUM = (3, 14)
SERVER_DEFAULT = "python3"
FIX = "Set the interpreter with /plugin configure io-guard, for example to python on Windows."


def answer(reply):
    sys.stdout.buffer.write(json.dumps(reply).encode("ascii"))


def server_python_is_new_enough(command):
    """Whether the command the io server starts from runs Python 3.14 or later."""
    probe = "import sys; print(sys.version_info >= (3, 14))"
    try:
        done = subprocess.run([command, "-c", probe], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and done.stdout.strip() == b"True"


def interpreter_warning():
    """The one warning a session gets when a Python io-guard needs is missing or too old, or None."""
    if sys.version_info[:2] < MINIMUM:
        found = ".".join(str(part) for part in sys.version_info[:3])
        return ("io-guard needs Python 3.14 or later, and " + sys.executable + " is " + found
                + ", so it checks nothing this session. " + FIX)
    command = os.environ.get("CLAUDE_PLUGIN_OPTION_PYTHON") or SERVER_DEFAULT
    if not server_python_is_new_enough(command):
        return ("io-guard's Python interpreter setting is " + json.dumps(command) + ", which does not start "
                "Python 3.14 or later, so the io server is off and nothing is checked this session. " + FIX)
    return None


def record(event_name, event):
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return
    now = time.gmtime()
    session = str(event.get("session_id") or "unknown-session")
    folder = Path(data) / "events" / time.strftime("%Y-%m", now)
    folder.mkdir(parents=True, exist_ok=True)
    line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", now), "session": session, "event": event_name,
            "tool": event.get("tool_name"), "surface": "command_hook", "noop": True}
    with (folder / (session + ".jsonl")).open("ab") as out:
        out.write((json.dumps(line) + "\n").encode("ascii"))


def main():
    event_name = sys.argv[1] if len(sys.argv) > 1 else ""
    raw = sys.stdin.buffer.read()
    try:
        event = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except ValueError:
        event = {}
    if not isinstance(event, dict):
        event = {}
    try:
        record(event_name, event)
    except OSError as error:
        sys.stderr.write("io-guard could not record the " + event_name + " event: " + str(error) + "\n")
    if event_name == "session_start":
        warning = interpreter_warning()
        if warning is not None:
            answer({"systemMessage": warning})
    return 0


if __name__ == "__main__":
    sys.exit(main())
