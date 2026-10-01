"""The heartbeat hook's answer for a running server, read before the check pipeline loads.

The UserPromptSubmit hook starts a new Python on every prompt, and the pipeline's imports are most of its
time. A heartbeat the session's io server wrote within FRESH_S, or one marked stopped, leaves
server.heartbeat nothing to say, so the hook answers without it. Any other state, a missing or unreadable file
among them, goes to the pipeline as before.
"""
import json
from collections.abc import Mapping
from datetime import datetime, timezone

from ioguard.lib import heartbeat
from ioguard.lib.folders import SESSION_ID, home_folder, session_file


def running(raw: bytes, env: Mapping[str, str]) -> bool:
    """Whether the event's session has an io server that beat within FRESH_S or stopped cleanly."""
    try:
        session = json.loads(raw.decode("utf-8"))["session_id"]
        if not isinstance(session, str) or not SESSION_ID.fullmatch(session):
            return False
        data = session_file(home_folder(env), session, "alive").read_bytes()
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return heartbeat.quiet(data, datetime.now(timezone.utc))
