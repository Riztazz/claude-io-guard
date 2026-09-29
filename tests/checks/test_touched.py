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

    def after(self, response: dict | None = None, command: str = "make"):
        """The command's PostToolUse, and what shell.touched found."""
        raw = events.post_tool_use("Bash", {"command": command}, response or events.bash_result(""), CWD)
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

    def test_a_change_to_gits_index_alone_names_nothing(self):
        cases = {"git add": ((entry("a.txt", " M"), entry("new.txt", "??")), (entry("a.txt", "M "),
                                                                             entry("new.txt", "A "))),
                 "git commit": ((entry("a.txt", "MM"),), (entry("a.txt", " M"),)),
                 "git reset": ((entry("a.txt", "M "),), (entry("a.txt", " M"),)),
                 "git rm --cached": ((), (entry("kept.txt", "D "), entry("kept.txt", "??")))}
        for name, (before, after) in cases.items():
            with self.subTest(name):
                session = Session(before=before)
                for each in {*before, *after}:
                    session.fs.files.setdefault(CWD / each.path, b"x\n")
                session.run(events.bash(name, CWD))
                session.git.current_status = GitStatus(after)
                self.assertEqual(session.after(), [], "the files' bytes did not move, so nothing is named")

    def test_staging_a_rename_made_earlier_names_nothing(self):
        renamed = StatusEntry("done/a.md", "R", "M", "open/a.md")
        session = Session(before=(renamed,))
        session.fs.files[CWD / "done" / "a.md"] = b"x\n"
        session.run(events.bash("git add done/a.md", CWD))
        session.git.current_status = GitStatus((entry("done/a.md", "A "), entry("open/a.md", "D ")))
        self.assertEqual(session.after(command="git add done/a.md"), [],
                         "open/a.md was gone before the command, so the command deleted nothing")

    def test_a_move_the_command_names_is_no_news(self):
        cases = {"git add then git mv of a new file": (
                     "git add open/a.md && git mv open/a.md done/", (entry("open/a.md", "??"),),
                     (entry("done/a.md", "A "),)),
                 "git mv of a tracked file": (
                     "git mv open/a.md done/a.md", (), (StatusEntry("done/a.md", "R", " ", "open/a.md"),)),
                 "mv of a tracked file": ("mv open/a.md done/a.md", (),
                                          (entry("open/a.md", " D"), entry("done/a.md", "??")))}
        for name, (command, before, after) in cases.items():
            with self.subTest(name):
                session = Session(before=before)
                session.fs.files[CWD / "open" / "a.md"] = b"task\n"
                session.ctx.session.read_profiles[CWD / "open" / "a.md"] = profile(b"task\n")
                session.run(events.bash(command, CWD))
                del session.fs.files[CWD / "open" / "a.md"]
                session.fs.files[CWD / "done" / "a.md"] = b"task\n"
                session.git.current_status = GitStatus(after)
                self.assertEqual(session.after(command=command), [],
                                 "a file the command moved on purpose is neither deleted nor created")

    def test_a_move_the_command_does_not_name_is_named_as_a_move(self):
        session = Session()
        session.fs.files[CWD / "open" / "a.md"] = b"task\n"
        session.ctx.session.read_profiles[CWD / "open" / "a.md"] = profile(b"task\n")
        session.run(events.bash("python tidy.py", CWD))
        del session.fs.files[CWD / "open" / "a.md"]
        session.fs.files[CWD / "done" / "a.md"] = b"task\n"
        session.git.current_status = GitStatus((entry("done/a.md", "??"),))
        found = session.after(command="python tidy.py")[0]
        self.assertEqual((found.message, found.fix.text),
                         ("This command moved open/a.md to done/a.md.",
                          "Use the files' new paths from now on."),
                         "a script's move is one move, not a deletion and a new file")

    def test_a_listed_file_whose_bytes_moved_is_still_named(self):
        session = Session(before=(entry("a.txt", " M"),))
        session.fs.files[CWD / "a.txt"] = b"x\n"
        session.run(events.bash("make", CWD))
        session.fs.write_atomic(CWD / "a.txt", b"y\n")
        session.git.current_status = GitStatus((entry("a.txt", "MM"),))
        self.assertIn("changed a.txt", session.after()[0].message, "a write to the file is a change")

    def test_a_tracked_file_a_script_changed_is_a_shell_write(self):
        found = {}
        for command in ("python fmt.py b.cpp", "make"):
            session = Session()
            session.git.tracked = frozenset({CWD / "b.cpp"})
            session.run(events.bash(command, CWD))
            session.git.current_status = GitStatus((entry("b.cpp", " M"),))
            found[command] = [(result.code, result.message) for result in session.after(command=command)]
        self.assertEqual([code for code, _ in found["python fmt.py b.cpp"]],
                         [Code.TOUCHED_BY_SHELL, Code.SHELL_WRITE], "a script's write skipped the checks")
        self.assertIn("fmt.py changed b.cpp, which git tracks", found["python fmt.py b.cpp"][1][1],
                      "the warning names the script and the file")
        self.assertEqual([code for code, _ in found["make"]], [Code.TOUCHED_BY_SHELL],
                         "a build that changes a file is no script run")

    def test_a_file_git_changed_is_not_blamed_on_the_script(self):
        blamed = {}
        for command in ("git mv a.cpp b.cpp && python check.py", "git checkout HEAD -- b.cpp; python m.py",
                        "cd Source && git mv x.cpp ../b.cpp && python ../check.py",
                        "git -C . checkout main; python check.py", "git stash pop && python check.py",
                        "git reset --hard && python check.py", "git mv $F b.cpp && python check.py",
                        "git checkout HEAD -- a.cpp; python m.py", "git add b.cpp && python check.py",
                        "git stash list && python check.py", "git rm -q c.cpp && python check.py",
                        "git reset -q -- b.cpp && python check.py"):
            session = Session()
            session.git.tracked = frozenset({CWD / "b.cpp"})
            session.run(events.bash(command, CWD))
            session.git.current_status = GitStatus((entry("b.cpp", " M"),))
            blamed[command] = Code.SHELL_WRITE in [result.code for result in session.after(command=command)]
        self.assertEqual([command for command, named in blamed.items() if named],
                         ["git checkout HEAD -- a.cpp; python m.py", "git add b.cpp && python check.py",
                          "git stash list && python check.py", "git rm -q c.cpp && python check.py",
                          "git reset -q -- b.cpp && python check.py"],
                         "a file git names is git's, a git command that can change any file blames no "
                         "script, and one that changes no file in the tree leaves the script named")

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
