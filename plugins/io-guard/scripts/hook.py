"""io-guard's command-hook entry point: pyrun hook.py <event>, with the hook event as JSON on stdin.

It writes one ASCII JSON answer to stdout, the check pipeline's through hooks.entry, and exits 0. On
session_start it also checks that this Python is 3.14 or later, and warns once when it is not. The io server
starts through the same launcher, scripts/pyrun, so the check covers the server's Python too. A crash before
the answer answers {} and logs GUARD_ERROR to stderr.

This file runs on older Pythons long enough to say that they are too old, so it avoids syntax newer than 3.8,
and it imports ioguard only on 3.14 or later.
"""
import json
import sys
import traceback

MINIMUM = (3, 14)
FIX = ("Install Python 3.14 or later, or set IOGUARD_PYTHON to its full path in the env block of "
       "~/.claude/settings.json.")


def answer(reply):
    sys.stdout.buffer.write(json.dumps(reply).encode("ascii"))


def interpreter_warning():
    """The one warning a session gets when this Python is older than 3.14, or None."""
    if sys.version_info[:2] >= MINIMUM:
        return None
    found = ".".join(str(part) for part in sys.version_info[:3])
    return ("io-guard needs Python 3.14 or later, and " + sys.executable + " is " + found
            + ", so it checks nothing this session. " + FIX)


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
