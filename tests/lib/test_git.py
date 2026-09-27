"""Git's output parses into typed values, and the live Git port answers from a real repository."""
import unittest

from ioguard.lib.git import (Git, GitError, LineRange, StatusEntry, parse_attributes, parse_ranges,
                             parse_status)
from tests.support.project import TemporaryProject


class GitOutputParses(unittest.TestCase):
    def test_status_reads_modified_untracked_and_renamed_entries(self):
        raw = b" M src/a.cpp\0?? new file.txt\0R  new.txt\0old.txt\0"
        self.assertEqual(parse_status(raw).entries,
                         (StatusEntry("src/a.cpp", " ", "M"), StatusEntry("new file.txt", "?", "?"),
                          StatusEntry("new.txt", "R", " ", "old.txt")),
                         "porcelain -z status gives each entry, and a rename carries its old path")

    def test_empty_status_has_no_entries(self):
        self.assertEqual(parse_status(b"").entries, (), "a clean tree has no status entries")

    def test_ranges_read_the_new_side_of_each_hunk(self):
        raw = b"@@ -3,2 +3,4 @@ ctx\n-a\n+b\n@@ -10 +12 @@\n@@ -20,3 +21,0 @@\n"
        self.assertEqual(parse_ranges(raw), (LineRange(3, 4), LineRange(12, 1), LineRange(21, 0)),
                         "a hunk with no count is one line, and a deletion has a count of 0")

    def test_attributes_read_as_name_to_value(self):
        raw = b"a.txt\0text\0auto\0a.txt\0eol\0lf\0"
        self.assertEqual(parse_attributes(raw), {"text": "auto", "eol": "lf"},
                         "check-attr -a -z gives each attribute and its value")


class LiveGitAnswers(unittest.TestCase):
    def test_a_real_repository_answers_every_port_call(self):
        with TemporaryProject({"a.txt": b"one\ntwo\n", "sub/b.txt": b"b\n"}, git=True) as root:
            git = Git()
            (root / "a.txt").write_bytes(b"one\nTWO\nthree\n")
            (root / "c.txt").write_bytes(b"new\n")
            self.assertEqual(git.root(root / "sub").resolve(), root.resolve(), "root finds the top level")
            self.assertTrue(git.is_tracked(root / "a.txt"), "a committed file is tracked")
            self.assertFalse(git.is_tracked(root / "c.txt"), "a new file is not tracked")
            self.assertEqual({entry.path for entry in git.status(root).entries}, {"a.txt", "c.txt"},
                             "status lists the modified file and the untracked one")
            self.assertEqual(git.changed_ranges(root / "a.txt"), (LineRange(2, 2),),
                             "the changed lines of a.txt are lines 2 and 3 of the new file")
            self.assertEqual(sorted(path.name for path in git.ls_files(root)), ["a.txt", "b.txt"],
                             "ls_files lists the tracked files")

    def test_staged_paths_and_their_stored_bytes(self):
        with TemporaryProject({"a.txt": b"one\r\n", "sub/b.txt": b"b\n"}, git=True) as root:
            git = Git()
            (root / "a.txt").write_bytes(b"one\n")
            (root / "sub" / "n.txt").write_bytes(b"new\n")
            (root / "sub" / "b.txt").write_bytes(b"not staged\n")
            git.run(root, "add", "a.txt", "sub/n.txt")
            self.assertEqual(sorted(git.staged(root)), ["a.txt", "sub/n.txt"],
                             "staged lists what the next commit adds or changes, and nothing unstaged")
            blobs = (git.blob(root, "HEAD:a.txt"), git.blob(root, ":a.txt"), git.blob(root, "HEAD:sub/n.txt"))
            self.assertEqual(blobs, (b"one\r\n", b"one\n", None),
                             "blob gives the committed and the staged bytes, and None for a file new to the "
                             "commit")

    def test_outside_a_repository_root_is_none(self):
        with TemporaryProject({"a.txt": b"x"}) as root:
            self.assertIsNone(Git().root(root), "a folder outside every repository has no root")

    def test_a_failed_git_call_raises_rather_than_answering(self):
        with TemporaryProject({"a.txt": b"x"}) as root:
            with self.assertRaises(GitError, msg="status outside a repository is a failure, not an empty "
                                                 "status"):
                Git().status(root)


if __name__ == "__main__":
    unittest.main()
