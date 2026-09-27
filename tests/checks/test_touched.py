"""shell.touched names the files a shell command changed, created or deleted, and what it did to the bytes of
the ones the agent had read."""
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeFs, FakeGit
from ioguard.lib.git import GitStatus, StatusEntry
from ioguard.lib.platform import Platform
from ioguard.lib.profile import profile
from ioguard.lib.results import Code
from tests.support import events

CWD = Path("C:/game")
READ = CWD / "Source" / "a.cpp"
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()


def entry(path: str, code: str) -> StatusEntry:
    return StatusEntry(path, code[0], code[1])


class Session:
    """A session that has read Source/a.cpp, around one Bash command."""

    def __init__(self, data: bytes = b"int a;\r\n", skip: list | None = None,
                 before: tuple[StatusEntry, ...] = ()) -> None:
        values = {**defaults(REGISTRY.keys()).values, "skip_trees": skip or []}
        self.fs, self.git = FakeFs({READ: data}), FakeGit(root=CWD, status=GitStatus(before))
        self.ctx = Context.fake(config=Config(MappingProxyType(values)), platform=WINDOWS, fs=self.fs,
                                git=self.git)
        self.ctx.session.read_profiles[READ] = profile(data)
        self.run(events.bash("make", CWD))

    def run(self, raw: dict):
        return Pipeline(REGISTRY).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), self.ctx)

    def after(self, response: dict | None = None):
        """The command's PostToolUse, and what shell.touched found."""
        raw = events.post_tool_use("Bash", {"command": "make"}, response or events.bash_result(""), CWD)
        outcome = self.run(raw)
        return [result for decision in outcome.decisions if decision.check_id == "shell.touched"
                for result in decision.results]


class TheCommandsChangesAreNamed(unittest.TestCase):
    def test_a_read_file_the_command_changed_is_named_with_the_step(self):
        session = Session()
        session.fs.write_atomic(READ, b"int b;\r\n")
        found = session.after()
        self.assertEqual((found[0].code, found[0].message, found[0].fix.text),
                         (Code.TOUCHED_BY_SHELL, "This command changed Source/a.cpp, read before it.",
                          "Read Source/a.cpp again before the next Edit."),
                         "the agent learns which file changed under it, and to read it again")

    def test_new_changed_and_deleted_files_come_from_git_status(self):
        session = Session(before=(entry("old.txt", " M"),))
        session.git.current_status = GitStatus((entry("old.txt", " M"), entry("tmp.py", "??"),
                                                entry("b.cpp", " M"), entry("gone.h", " D")))
        found = session.after()
        self.assertEqual(found[0].message, "This command changed b.cpp, created tmp.py and deleted gone.h.",
                         "what git status gained is named, and what it already showed is not")

    def test_skip_trees_leave_changes_out(self):
        session = Session(skip=["Content/**"])
        session.git.current_status = GitStatus((entry("Content/Hero.uasset", " M"),
                                                entry("Content/New.uasset", "??")))
        self.assertEqual(session.after(), [], "changes under a skipped tree are left out")

    def test_a_command_that_changed_nothing_says_nothing(self):
        self.assertEqual(Session().after(), [], "no change, no report")

    def test_bash_edit_diff_adds_the_files_it_names(self):
        session = Session()
        response = {**events.bash_result(""), "files": [{"filePath": str(READ), "hunks": []}]}
        found = session.after(response)
        self.assertIn("Source/a.cpp, read before it", found[0].message,
                      "a bashEditDiff names a changed file even when its size and time did not move")


class WhatTheCommandDidToTheBytes(unittest.TestCase):
    def test_a_script_that_converted_the_endings_is_reported(self):
        session = Session(b"int a;\r\nint b;\r\n")
        session.fs.write_atomic(READ, b"int a;\nint b;\n")
        found = session.after()
        self.assertEqual([result.code for result in found], [Code.TOUCHED_BY_SHELL, Code.EOL_MISMATCH],
                         "the endings the command rewrote are named after the file")
        self.assertEqual(found[1].message, "This command changed a.cpp from CRLF to LF line endings.",
                         "the message says what the command did")

    def test_the_same_change_is_reported_once(self):
        session = Session(b"int a;\r\n")
        session.fs.write_atomic(READ, b"int a;\n")
        session.after()
        session.run(events.bash("make", CWD))
        self.assertEqual(session.after(), [], "the profile moves on, so the next command is judged alone")


if __name__ == "__main__":
    unittest.main()
