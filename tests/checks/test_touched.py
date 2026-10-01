"""shell.touched names the files a shell command changed, created or deleted, and what it did to the bytes of
the ones the agent had read."""
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks import touched
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


class ACommandThatOnlyReadsIsNotWatched(unittest.TestCase):
    def test_a_read_only_command_runs_no_git_status(self):
        session, asked = Session(), []
        real = session.git.status
        session.git.status = lambda root: asked.append(root) or real(root)
        session.after()
        session.run(events.bash("git log --oneline -3", CWD))
        session.fs.write_atomic(READ, b"int b;\r\n")
        self.assertEqual((session.after(command="git log --oneline -3"), asked), ([], [CWD]),
                         "only make's PostToolUse asks git, since git log changes no file")


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

    def test_a_git_mv_of_a_new_file_never_read_is_no_news(self):
        command = "git add open/b.md && git mv open/b.md done/"
        session = Session(before=(entry("open/b.md", "??"),))
        session.fs.files[CWD / "open" / "b.md"] = b"task\n"
        session.run(events.bash(command, CWD))
        del session.fs.files[CWD / "open" / "b.md"]
        session.fs.files[CWD / "done" / "b.md"] = b"task\n"
        session.git.current_status = GitStatus((entry("done/b.md", "A "),))
        self.assertEqual(session.after(command=command), [],
                         "git lists no D for a file it never committed, and the move is still seen")

    def test_untracked_files_the_command_renames_are_no_news(self):
        command = 'for s in a b; do mv "fable-$s.md" "$n-$s.md"; done'
        session = Session(before=(entry("fable-a.md", "??"), entry("fable-b.md", "??")))
        session.fs.files.update({CWD / "fable-a.md": b"task a\n", CWD / "fable-b.md": b"b\n"})
        session.run(events.bash(command, CWD))
        for old, new in (("fable-a.md", "129-a.md"), ("fable-b.md", "130-b.md")):
            session.fs.files[CWD / new] = session.fs.files.pop(CWD / old)
        session.git.current_status = GitStatus((entry("129-a.md", "??"), entry("130-b.md", "??")))
        self.assertEqual(session.after(command=command), [],
                         "a rename the command names changes a file's name, and it creates nothing")

    def test_a_named_rename_pairs_each_path_with_the_one_of_its_size(self):
        fs = FakeFs({CWD / "129-a.md": b"task a\n", CWD / "130-b.md": b"b\n"})
        ctx = Context.fake(platform=WINDOWS, fs=fs)
        gone, arrived = [CWD / "fable-a.md", CWD / "fable-b.md"], [CWD / "130-b.md", CWD / "129-a.md"]
        sizes = {CWD / "fable-a.md": 7, CWD / "fable-b.md": 2}
        self.assertEqual(touched.moves(gone, arrived, {}, sizes, True, ctx),
                         [(CWD / "fable-b.md", CWD / "130-b.md"), (CWD / "fable-a.md", CWD / "129-a.md")],
                         "with as many paths gone as arrived, each pairs with the one of the same size")

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

    def test_a_file_a_script_writes_unasked_is_changed_by_running_the_script_again(self):
        session = Session()
        session.git.tracked = frozenset({CWD / "SKILL.md"})
        session.run(events.bash("python tools/skill.py", CWD))
        session.git.current_status = GitStatus((entry("SKILL.md", " M"),))
        written = [result for result in session.after(command="python tools/skill.py")
                   if result.code is Code.SHELL_WRITE][0]
        self.assertEqual(written.fix.text,
                         "Change SKILL.md by changing tools/skill.py or what it reads, then run it again.",
                         "a file a generator writes is changed through the generator, never by hand")

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


class OnlyWhatTheCommandDidIsItsOwn(unittest.TestCase):
    def test_a_write_of_the_sessions_own_while_the_command_ran_is_left_out(self):
        session = Session()
        readme = CWD / "README.md"
        session.fs.files[readme] = b"old\n"
        session.run(events.write(readme, "new\n", CWD, tool_use_id="toolu_write"))
        session.fs.write_atomic(readme, b"new\n")
        session.run(events.post_tool_use("Write", {"file_path": str(readme), "content": "new\n"},
                                         {"type": "update", "filePath": str(readme)}, CWD,
                                         tool_use_id="toolu_write"))
        session.git.current_status = GitStatus((entry("README.md", " M"),))
        self.assertEqual(session.after(), [], "the session's own Write is not the command's change")

    def test_another_shell_command_beside_it_is_named_as_such(self):
        session = Session()
        session.run(events.bash("python gen.py", CWD, tool_use_id="toolu_other"))
        session.run(events.post_tool_use("Bash", {"command": "python gen.py"}, events.bash_result(""), CWD,
                                         tool_use_id="toolu_other"))
        session.git.current_status = GitStatus((entry("gen.txt", "??"),))
        self.assertEqual(session.after()[0].message,
                         "This command, or another command that ran at the same time, created gen.txt.",
                         "a change during the window is not pinned on this command alone")

    def test_a_move_the_command_names_and_commits_is_no_news(self):
        command = "git mv open/a.md done/ && git commit -q -m done"
        session = Session(before=(entry("open/a.md", " M"),))
        session.fs.files[CWD / "open" / "a.md"] = b"task\n"
        session.ctx.session.read_profiles[CWD / "open" / "a.md"] = profile(b"task\n")
        session.run(events.bash(command, CWD))
        del session.fs.files[CWD / "open" / "a.md"]
        session.fs.files[CWD / "done" / "a.md"] = b"task\n"
        session.git.current_status = GitStatus(())
        self.assertEqual(session.after(command=command), [],
                         "the commit hid the file's arrival, and the move is still the command's own")


class TheAdviceFitsWhatTheCommandDid(unittest.TestCase):
    def test_a_changed_file_never_read_needs_no_advice(self):
        session = Session()
        session.run(events.bash("python tools/skill.py", CWD))
        session.git.current_status = GitStatus((entry("SKILL.md", " M"),))
        found = session.after(command="python tools/skill.py")[0]
        self.assertEqual((found.message, found.fix), ("This command changed SKILL.md.", None),
                         "the agent's view of a file it never read is not stale, and nothing was created")

    def test_each_kind_brings_its_own_step(self):
        session = Session()
        session.fs.write_atomic(READ, b"int b;\r\n")
        session.git.current_status = GitStatus((entry("tmp.py", "??"),))
        self.assertEqual(session.after()[0].fix.text,
                         "Read Source/a.cpp again before the next Edit. Delete any new file the task does "
                         "not need, and keep the rest on purpose.",
                         "a read file changed and a file created each bring their step")


class AnImageTheCommandRedrewIsNamedForWhatItIs(unittest.TestCase):
    def test_an_image_in_the_scratchpad_is_read_again_to_be_seen(self):
        scratch = Path("C:/tmp/claude/s1/scratchpad")
        png = scratch / "fab" / "board.png"
        session = Session()
        session.fs.files[png] = b"\x89PNG\r\n\x1a\n\x00\x00old"
        session.ctx.session.read_profiles[png] = profile(session.fs.files[png])
        session.run(events.bash("python draw.py", CWD, scratchpad_dir=str(scratch)))
        session.fs.write_atomic(png, b"\x89PNG\r\n\x1a\n\x00\x00new!")
        raw = events.post_tool_use("Bash", {"command": "python draw.py"}, events.bash_result(""), CWD,
                                   scratchpad_dir=str(scratch))
        found = [result for decision in session.run(raw).decisions if decision.check_id == "shell.touched"
                 for result in decision.results]
        self.assertEqual((found[0].message, found[0].fix.text),
                         ("This command changed scratchpad/fab/board.png, read before it.",
                          "Read scratchpad/fab/board.png again to see what the command made of it."),
                         "no Edit applies to an image, and a scratchpad path is short")


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


class TheReportRendersARecordOfChanges(unittest.TestCase):
    def test_a_record_of_changes_renders_on_its_own(self):
        changes = touched.Changes(read=(), changed=(CWD / "b.h",), created=(CWD / "n.txt",), deleted=(),
                                  moved=((CWD / "a.txt", CWD / "c.txt"),), named_move=False, beside=False)
        result = touched.summary(changes, frozenset(), CWD, None, 8, "Bash", "win32")
        self.assertEqual((result.message, result.fix.text),
                         ("This command changed b.h, created n.txt and moved a.txt to c.txt.",
                          "Delete any new file the task does not need, and keep the rest on purpose. Use the "
                          "files' new paths from now on."),
                         "the record alone decides the message and the steps")

    def test_a_record_with_no_change_renders_nothing(self):
        changes = touched.Changes((), (), (), (), (), named_move=False, beside=False)
        self.assertIsNone(touched.summary(changes, frozenset(), CWD, None, 8, "Bash", "win32"),
                          "a command that changed nothing gets no report")


if __name__ == "__main__":
    unittest.main()
