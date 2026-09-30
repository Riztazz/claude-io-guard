"""read.profile adds a file's profile line after each Read, a warning line for bytes a write can break, and
keeps the hash of what the agent read."""
import time
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.profile import profile
from tests.support import events

CWD = Path("C:/project")
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()


def read(data: bytes | None, path: str = "C:/project/a.txt", **config):
    raw = events.post_tool_use("Read", {"file_path": path}, {"type": "text"}, CWD)
    event = Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS)
    values = {**defaults(REGISTRY.keys()).values, **{f"checks.read.profile.{key}": value
                                                      for key, value in config.items()}}
    ctx = Context.fake(files={} if data is None else {event.file_path: data},
                       config=type(defaults())(values), platform=WINDOWS)
    return Pipeline(REGISTRY).run(event, ctx), ctx, event


class TheProfileLine(unittest.TestCase):
    def test_a_read_gets_one_profile_line(self):
        outcome, _, _ = read(b"\xef\xbb\xbfint x;\r\n\tint y;\r\n")
        self.assertEqual(outcome.context, ("io-guard: CRLF, BOM, UTF-8, tabs, 2 lines",),
                         "the line names the endings, the BOM, the encoding, the indent and the length")

    def test_a_hazard_adds_one_warning_line(self):
        outcome, _, _ = read(b"one\r\ntwo\nthree\r\n")
        self.assertEqual(len(outcome.context), 2, "a profile line, then one warning line")
        self.assertIn("mixes line endings", outcome.context[1], "the warning names the hazard")

    def test_a_background_tasks_output_file_gets_no_line_and_a_project_file_still_does(self):
        mixed = b"one\r\ntwo\r\n[exited with code 0]\n"
        task = f"C:/Temp/claude/C--project/{events.SESSION_ID}/tasks/b1.output"
        outcome, ctx, event = read(mixed, task)
        self.assertEqual((outcome.context, event.file_path in ctx.session.read_profiles), ((), False),
                         "nobody edits Claude Code's own output file, so it gets no line and no profile")
        outcome, _, _ = read(mixed, "C:/project/tasks/b1.output")
        self.assertEqual(["mixes line endings" in line for line in outcome.context], [False, True],
                         "a project's file that mixes endings keeps its line and its warning")

    def test_a_binary_a_missing_or_a_too_large_file_gets_no_line(self):
        for data, config in ((b"\x89PNG\r\n\x1a\n\x00\x00", {}), (None, {}), (b"a\n" * 10, {"max_bytes": 5})):
            with self.subTest(data=data, config=config):
                outcome, _, _ = read(data, **config)
                self.assertEqual((outcome.verdict, outcome.context), (Verdict.OBSERVE, ()),
                                 "an image, a vanished file or a file past max_bytes adds nothing")


class TheProfileOfWhatWasRead(unittest.TestCase):
    def test_the_session_keeps_the_profile(self):
        data = b"one\r\ntwo\r\n"
        _, ctx, event = read(data)
        self.assertEqual(ctx.session.read_profiles[event.file_path], profile(data),
                         "the checks that compare a later change with these bytes read this profile")

    def test_a_megabyte_adds_little_time(self):
        data = b"".join(b"    line %06d of a large source file\r\n" % number for number in range(26000))
        started = time.perf_counter()
        read(data[:1 << 20])
        self.assertLess(time.perf_counter() - started, 0.5,
                        "the budget is 50 ms, and this bound catches only a pathological slowdown")


if __name__ == "__main__":
    unittest.main()
