"""io.stage stages the chosen hunks of one file in a real repository, by lines or by the journal's task tag,
keeps the index bytes as git add would, and never commits."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ioguard.lib import journal
from ioguard.lib.context import Context, LiveFs, SessionState
from ioguard.lib.git import Git
from ioguard.lib.platform import detect
from ioguard.lib.results import Code
from ioguard.mcp.in_place import Place
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_edit import EditInput, EditPair, edit
from ioguard.mcp.tools_history import StageInput, stage
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolFailure
from tests.support.project import TemporaryProject

LINES = b"".join(f"line {number}\n".encode() for number in range(1, 31))


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True,
                          check=True, timeout=60).stdout


class StageTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-stage-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def context(self) -> Context:
        return Context.fake(platform=detect(), fs=LiveFs(), git=Git(), data_dir=self.home,
                            session=SessionState.shared(self.home, "s1"))

    @staticmethod
    def call(handler, given, ctx: Context, root: Path):
        return handler(given, ToolCall(lambda: ctx, CancelToken(), root, None))

    def refusal(self, given: StageInput, ctx: Context, root: Path):
        with self.assertRaises(ToolFailure) as failure:
            self.call(stage, given, ctx, root)
        return failure.exception.result


class TwoOfThreeHunksAreStaged(StageTest):
    def test_the_third_stays_unstaged_and_git_diff_cached_shows_exactly_two(self):
        with TemporaryProject({"a.txt": LINES}, git=True) as root:
            changed = LINES.replace(b"line 3\n", b"LINE 3\n").replace(b"line 15\n", b"LINE 15\n")
            (root / "a.txt").write_bytes(changed.replace(b"line 27\n", b"LINE 27\n"))
            done = self.call(stage, StageInput("a.txt", [Place(3, 3), Place(27, 27)]), self.context(), root)
            cached = git(root, "diff", "--cached", "-U0", "--", "a.txt")
            left = git(root, "diff", "-U0", "--", "a.txt")
            self.assertEqual((done.staged, done.left), ([Place(3, 3), Place(27, 27)], [Place(15, 15)]),
                             "the result names the two hunks staged and the one left")
            self.assertEqual(cached.count(b"\n@@") + cached.startswith(b"@@"), 2, "the index holds two hunks")
            self.assertIn(b"+LINE 3", cached, "line 3's change is staged")
            self.assertIn(b"+LINE 27", cached, "line 27's change is staged")
            self.assertEqual([line for line in left.splitlines() if line.startswith(b"+L")], [b"+LINE 15"],
                             "only line 15's change is left in the working tree's diff")
            self.assertEqual(git(root, "rev-list", "--count", "HEAD").strip(), b"1", "nothing was committed")


class TheIndexTakesTheBytesGitAddWould(StageTest):
    def test_every_hunk_of_a_crlf_file_stages_to_the_blob_git_add_makes(self):
        crlf = LINES.replace(b"\n", b"\r\n")
        with TemporaryProject({"a.txt": crlf, ".gitattributes": b"*.txt -text\n"}, git=True) as root:
            (root / "a.txt").write_bytes(crlf.replace(b"line 2\r\n", b"two\r\n").replace(b"line 9\r\n", b""))
            self.call(stage, StageInput("a.txt", [Place(1, 30)]), self.context(), root)
            staged = git(root, "rev-parse", ":a.txt").strip()
            added = git(root, "hash-object", "--no-filters", "a.txt").strip()
            self.assertEqual(staged, added,
                             "the staged blob is the working file's bytes, CRLF and all (BYT-10)")


class ATaskTagStagesTheHunksTheJournalGivesIt(StageTest):
    def test_only_the_tagged_task_hunks_are_staged(self):
        with TemporaryProject({"a.py": LINES}, git=True) as root:
            ctx = self.context()
            ctx.session.tag = "rename"
            self.call(edit, EditInput("a.py", [EditPair("line 4\n", "renamed 4\n")]), ctx, root)
            ctx.session.tag = "other"
            self.call(edit, EditInput("a.py", [EditPair("line 20\n", "other 20\n")]), ctx, root)
            done = self.call(stage, StageInput("a.py", tag="rename"), ctx, root)
            cached = git(root, "diff", "--cached", "--", "a.py")
            self.assertEqual((done.staged, done.left), ([Place(4, 4)], [Place(20, 20)]),
                             "the journal gives line 4 to rename and line 20 to other")
            self.assertIn(b"+renamed 4", cached, "the rename task's line is staged")
            self.assertNotIn(b"other 20", cached, "the other task's line is not")
            self.assertEqual(len(list(journal.entries(self.home))), 2, "each io.edit was journaled once")


class StagingRefusesWhatItCannotDo(StageTest):
    def test_lines_that_meet_no_hunk_name_the_hunks_there_are(self):
        with TemporaryProject({"a.txt": LINES}, git=True) as root:
            (root / "a.txt").write_bytes(LINES.replace(b"line 5\n", b"LINE 5\n"))
            result = self.refusal(StageInput("a.txt", [Place(10, 12)]), self.context(), root)
            self.assertEqual(result.code, Code.HUNK_NOT_FOUND, "no hunk meets lines 10 to 12")
            self.assertIn("line 5", result.message, "the message lists where the hunks are")

    def test_an_untracked_file_names_git_add_n(self):
        with TemporaryProject({}, git=True) as root:
            (root / "new.txt").write_bytes(b"x\n")
            result = self.refusal(StageInput("new.txt", [Place(1, 1)]), self.context(), root)
            self.assertEqual((result.code, "git add -N" in result.fix.text), (Code.STAGE_FAILED, True),
                             "a file git does not track has no hunks until git add -N")

    def test_lines_and_a_tag_together_are_not_one_call(self):
        with TemporaryProject({"a.txt": LINES}, git=True) as root:
            with self.assertRaises(InvalidArguments):
                self.call(stage, StageInput("a.txt", [Place(1, 1)], "rename"), self.context(), root)


if __name__ == "__main__":
    unittest.main()
