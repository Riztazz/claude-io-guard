"""journal.write records each Edit and Write with the lines it changed and the session's task tag, and leaves
the snapshot for verify.write, which runs after it."""
import shutil
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks.conform_edit import ConformEdit
from ioguard.checks.conform_write import ConformWrite
from ioguard.checks.journal_write import JournalWrite
from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.checks.verify_write import VerifyWrite
from ioguard.lib import journal
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context, SessionState, Snapshot
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.profile import profile
from tests.support import events

PROJECT = Path("C:/project")
PATH = PROJECT / "a.py"
WINDOWS = Platform("win32", True)


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-journal-write-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def edited(self, before: bytes | None, after: bytes, tag: str | None = "pass", home: Path | None = None,
               keep_bytes: bool = True):
        home = self.home if home is None else home
        ctx = Context.fake({PATH: after}, platform=WINDOWS, data_dir=home,
                           session=SessionState.shared(home, "s1"), env={"CLAUDE_PROJECT_DIR": str(PROJECT)})
        ctx.session.tag = tag
        kept = before if keep_bytes else None
        tool_input = {"file_path": str(PATH), "old_string": "b", "new_string": "B"}
        found = None if before is None else profile(before)
        ctx.session.keep_snapshot(events.TOOL_USE_ID, Snapshot(PATH, found, kept, tool_input))
        registry = Registry()
        for check in (ConformWrite, ConformEdit, JournalWrite, VerifyWrite):
            registry.register(check)
        raw = events.post_tool_use("Edit", tool_input, {"filePath": str(PATH)}, PROJECT)
        Pipeline(registry).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx)
        return ctx


class AnEditIsJournaled(JournalTest):
    def test_the_line_the_tool_and_the_tag_are_recorded(self):
        self.edited(b"a\nb\nc\n", b"a\nB\nc\n")
        [entry] = journal.entries(self.home)
        self.assertEqual((entry.path, entry.tool, entry.tag, entry.session, entry.changed.lines),
                         ("C:/project/a.py", "Edit", "pass", "s1", ((2, 2),)),
                         "the journal names the file, the Edit, the task io.snapshot tagged, and line 2")

    def test_verify_write_still_takes_the_snapshot_after_the_journal(self):
        ctx = self.edited(b"a\nb\nc\n", b"a\nB\nc\n")
        self.assertIsNone(ctx.session.peek_snapshot(events.TOOL_USE_ID),
                          "verify.write ran after journal.write and took the snapshot it left")

    def test_a_file_too_large_to_keep_records_nothing(self):
        self.edited(b"a\nb\n", b"a\nB\n", keep_bytes=False)
        self.assertEqual(list(journal.entries(self.home)), [], "with no bytes before, nothing is compared")

    def test_a_file_the_write_made_is_new_from_line_one(self):
        self.edited(None, b"x\ny\n", tag=None)
        [entry] = journal.entries(self.home)
        self.assertEqual((entry.changed.lines, entry.tag), (((1, 2),), None),
                         "a file the Write made is new from line 1, with no tag before any snapshot")


class TheJournalNeedsNoVerifyWrite(JournalTest):
    def test_with_verify_write_off_an_edit_is_still_journaled(self):
        registry = Registry()
        for check in (ConformWrite, ConformEdit, JournalWrite, VerifyWrite):
            registry.register(check)
        values = {**defaults(registry.keys()).values, "checks.verify.write.enabled": False}
        ctx = Context.fake({PATH: b"a\nb\nc\n"}, config=Config(MappingProxyType(values)), platform=WINDOWS,
                           data_dir=self.home, session=SessionState.shared(self.home, "s1"),
                           env={"CLAUDE_PROJECT_DIR": str(PROJECT)})
        tool_input = {"file_path": str(PATH), "old_string": "b", "new_string": "B"}
        for raw in (events.edit(PATH, "b", "B", PROJECT),
                    events.post_tool_use("Edit", tool_input, {"filePath": str(PATH)}, PROJECT)):
            Pipeline(registry).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx)
            ctx.fs.files[PATH] = b"a\nB\nc\n"
        [entry] = journal.entries(self.home)
        self.assertEqual(entry.changed.lines, ((2, 2),), "the journal keeps its own snapshot of the file")
        self.assertIsNone(ctx.session.peek_snapshot(events.TOOL_USE_ID), "and takes it when it is done")


if __name__ == "__main__":
    unittest.main()
