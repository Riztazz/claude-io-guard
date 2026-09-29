"""restore.ask puts an io.restore call to the user when it would replace files that changed since their
snapshot, and leaves every other call alone."""
import shutil
import tempfile
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.checks.restore_ask import RestoreAsk
from ioguard.lib import snapshots
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeClock
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, callable_name
from tests.support import events

PROJECT = Path("C:/project")
WINDOWS = Platform("win32", True)


class RestoreAskTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-restore-ask-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.clock = FakeClock()
        files = [(PROJECT / f"f{number}.txt", b"kept\n") for number in range(12)]
        snapshots.take(self.home, "pass", PROJECT, files, self.clock.now())

    def decided(self, files: dict, tool_input: dict, tool_name: str = callable_name("io.restore")):
        ctx = Context.fake(files, platform=WINDOWS, data_dir=self.home, clock=self.clock,
                           env={"CLAUDE_PROJECT_DIR": str(PROJECT)})
        registry = Registry()
        registry.register(RestoreAsk)
        raw = events.pre_tool_use(tool_name, tool_input, PROJECT)
        return Pipeline(registry).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx), ctx


class ARestoreOverEditsIsPutToTheUser(RestoreAskTest):
    def test_the_question_names_the_files_and_the_key_is_recorded(self):
        edited = {PROJECT / f"f{number}.txt": b"edited\n" for number in range(12)}
        outcome, ctx = self.decided(edited, {"tag": "pass"})
        result = outcome.decisions[0].results[0]
        self.assertEqual((outcome.verdict, result.code), (Verdict.ASK, Code.RESTORE_ASKED),
                         "a restore that loses edits needs the user's yes")
        self.assertIn("and 2 more", result.message, "ten files are named, and the rest counted")
        self.assertEqual(list(ctx.session.asked), [events.TOOL_USE_ID],
                         "io.restore finds the question it may answer, by its tool use id")

    def test_a_restore_of_unchanged_files_and_other_calls_are_left_alone(self):
        same = {PROJECT / f"f{number}.txt": b"kept\n" for number in range(12)}
        cases = {"unchanged": (same, {"tag": "pass"}, callable_name("io.restore")),
                 "unknown tag": (same, {"tag": "other"}, callable_name("io.restore")),
                 "another tool": ({}, {"tag": "pass"}, callable_name("io.run"))}
        for name, (files, tool_input, tool) in cases.items():
            with self.subTest(name):
                outcome, ctx = self.decided(files, tool_input, tool)
                self.assertEqual((outcome.verdict, ctx.session.asked), (Verdict.OBSERVE, {}),
                                 "nothing to lose, or nothing to restore, asks nothing")


if __name__ == "__main__":
    unittest.main()
