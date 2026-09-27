"""io-guard's command-hook entry point: python hook.py <event>, with the hook event as JSON on stdin.

It writes one ASCII JSON answer to stdout, the check pipeline's through hooks.entry, and exits 0. On
session_start it also checks that this Python and the interpreter the io server starts from are both 3.14 or
later, and warns once when either is not. A crash before the answer answers {} and logs GUARD_ERROR to stderr.

This file runs on older Pythons long enough to say that they are too old, so it avoids syntax newer than 3.8,
and it imports ioguard only on 3.14 or later.
"""
import json
import os
import subprocess
import sys
import traceback

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


def guard(raw):
    """The pipeline's answer to the event."""
    from ioguard.hooks.entry import run_event
    from ioguard.lib.events import Surface
    return run_event(json.loads(raw.decode("utf-8")), Surface.COMMAND_HOOK)


def main():
    event_name = sys.argv[1] if len(sys.argv) > 1 else ""
    raw = sys.stdin.buffer.read()
    reply = {}
    if sys.version_info[:2] >= MINIMUM:
        try:
            reply = guard(raw)
        except Exception:
            sys.stderr.write("GUARD_ERROR: io-guard's " + event_name + " hook failed, so it answered {} and "
                             "let the session go on.\n" + traceback.format_exc())
            reply = {}
    if event_name == "session_start":
        warning = interpreter_warning()
        if warning is not None:
            reply["systemMessage"] = "\n".join(part for part in (warning, reply.get("systemMessage")) if part)
    answer(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
