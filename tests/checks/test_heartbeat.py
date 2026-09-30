"""server.heartbeat tells the user once, at the start of a turn, that the io server died or never started."""
import json
import unittest
from datetime import timedelta
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import defaults
from ioguard.lib.context import Context, session_file
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import START, FakeClock, FakeFs
from ioguard.lib.heartbeat import Era, Heartbeat
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code
from tests.support import events

CWD = Path("C:/project")
DATA = Path("C:/data")
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()
ALIVE = session_file(DATA, events.SESSION_ID, "alive")
CLAUDE = Path("C:/Users/u/.claude")


def prompt() -> dict:
    return {**events.base("UserPromptSubmit", CWD), "prompt": "go on"}


def turn(ctx: Context):
    """What the heartbeat check says at the start of a turn."""
    outcome = Pipeline(REGISTRY).run(Event.from_hook_json(prompt(), Surface.COMMAND_HOOK, WINDOWS), ctx)
    return [result for decision in outcome.decisions if decision.check_id == "server.heartbeat"
            for result in decision.results], outcome


def context(beat_age_s: float | None, stopped: bool = False, failed_age_s: float | None = None) -> Context:
    files = {}
    if beat_age_s is not None:
        beat = START - timedelta(seconds=beat_age_s)
        files[ALIVE] = Heartbeat(4242, events.SESSION_ID, Era.LEGACY, beat - timedelta(minutes=5), beat,
                                 beat if stopped else None).encode()
    if failed_age_s is not None:
        failed_ms = (START - timedelta(seconds=failed_age_s)).timestamp() * 1000
        entry = {"plugin:io-guard:io": {"timestamp": failed_ms, "id": "2a482f078df864d7"}}
        files[CLAUDE / "mcp-needs-auth-cache.json"] = json.dumps(entry).encode("ascii")
    return Context.fake(config=defaults(REGISTRY.keys()), platform=WINDOWS, fs=FakeFs(files),
                        clock=FakeClock(), data_dir=DATA, env={"CLAUDE_CONFIG_DIR": str(CLAUDE)})


class AStoppedServerIsNamedOnce(unittest.TestCase):
    def test_a_beat_older_than_stale_s_warns_the_user_once(self):
        ctx = context(beat_age_s=31)
        found, outcome = turn(ctx)
        self.assertEqual(found[0].code, Code.SERVER_DOWN, "a server that stopped beating has died")
        self.assertIn("so the tool calls since then ran without its checks", outcome.user_message,
                      "the user reads it, because only the user can see why the server cannot start")
        self.assertEqual(turn(ctx)[0], [], "and the next turn says nothing new")

    def test_at_stale_s_the_server_still_counts_as_running(self):
        for age, expected in ((30, []), (31, [Code.SERVER_DOWN])):
            with self.subTest(age=age):
                self.assertEqual([result.code for result in turn(context(age))[0]], expected,
                                 "the server writes every 5 seconds, so 30 seconds of silence is a stop")

    def test_a_clean_stop_or_a_server_that_never_beat_says_nothing(self):
        for ctx in (context(beat_age_s=600, stopped=True), context(beat_age_s=None)):
            with self.subTest():
                self.assertEqual(turn(ctx)[0], [],
                                 "a stop the server wrote is not a death, and no file means no server ran")


class AServerClaudeCodeSkippedIsNamed(unittest.TestCase):
    def test_a_server_skipped_after_a_failed_start_is_named_with_when_it_returns(self):
        found, outcome = turn(context(beat_age_s=None, failed_age_s=300))
        self.assertEqual(found[0].code, Code.SERVER_DOWN, "the server never started this session")
        self.assertIn("did not start io-guard's io server this session, because it failed to start at",
                      found[0].message, "Claude Code's own cache says why, and until when")
        self.assertIn("Run /mcp", outcome.user_message, "and the user can reconnect it")

    def test_after_fifteen_minutes_claude_code_tries_again_and_nothing_is_said(self):
        for age, expected in ((899, [Code.SERVER_DOWN]), (901, [])):
            with self.subTest(age=age):
                found = turn(context(None, failed_age_s=age))[0]
                self.assertEqual([result.code for result in found], expected,
                                 "Claude Code skips a failed plugin server for 900 seconds")

    def test_a_running_server_is_not_blamed_for_an_old_cache_entry(self):
        self.assertEqual(turn(context(beat_age_s=2, failed_age_s=60))[0], [],
                         "this session's heartbeat shows the server running")


if __name__ == "__main__":
    unittest.main()
