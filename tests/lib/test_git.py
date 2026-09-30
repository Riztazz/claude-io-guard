"""Git's output parses into typed values, and the live Git port answers from a real repository."""
import os
import sys
import unittest
from pathlib import Path

from ioguard.lib import proc

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

    def test_a_rename_in_either_column_carries_its_old_path(self):
        raw = b" R b.txt\0a.txt\0 M c.txt\0"
        self.assertEqual(parse_status(raw).entries,
                         (StatusEntry("b.txt", " ", "R", "a.txt"), StatusEntry("c.txt", " ", "M")),
                         "a worktree rename, as git add -N gives, reads its old path too")

    def test_empty_status_has_no_entries(self):
        self.assertEqual(parse_status(b"").entries, (), "a clean tree has no status entries")

    def test_ranges_read_the_new_side_of_each_hunk(self):
        raw = b"@@ -3,2 +3,4 @@ ctx\n-a\n+b\n@@ -10 +12 @@\n@@ -20,3 +21,0 @@\n"
        self.assertEqual(parse_ranges(raw), (LineRange(3, 4), LineRange(12, 1), LineRange(21, 0)),
                         "a hunk with no count is one line, and a deletion has a count of 0")

    def test_a_path_that_is_not_utf8_keeps_its_bytes(self):
        raw = b" M caf\xe9.txt\0?? ok.txt\0"
        entries = parse_status(raw).entries
        self.assertEqual((len(entries), entries[0].path.encode("utf-8", "surrogateescape")),
                         (2, b"caf\xe9.txt"),
                         "a Latin-1 file name parses, with its bytes kept for the file system")

    def test_a_call_past_the_deadline_does_not_start_git(self):
        late = Git().within(-1.0)
        with self.assertRaises(GitError) as refused:
            late.run(Path("."), "status")
        self.assertIn("time budget had run out", str(refused.exception),
                      "a check's git call past the hook's budget raises and names why")
        self.assertLessEqual(Git().within(0.5).time_left(("status",)), 0.5,
                             "a call within the budget gets at most what is left of it")

    def test_git_runs_the_program_it_was_given_within_a_budget_too(self):
        program = proc.on_path("git", os.environ)
        with TemporaryProject({"a.txt": b"a\n"}, git=True) as project:
            root = Git(program).within(5.0).root(project / "a.txt")
        missing = Git("io-guard-no-such-git").run(Path.cwd(), "--version")
        self.assertEqual((root, missing.ok), (project, False),
                         "a git named by its full path answers, and a budgeted copy keeps the same program")

    def test_an_ignored_path_is_ignored_even_before_it_exists(self):
        with TemporaryProject({".gitignore": b"/build/\n", "a.txt": b"a\n"}, git=True) as project:
            git = Git()
            found = (git.is_ignored(project / "build" / "new" / "x.py"), git.is_ignored(project / "a.txt"),
                     git.is_ignored(project / "tools" / "y.py"))
        self.assertEqual(found, (True, False, False),
                         "check-ignore answers for a path under an ignored folder that does not exist yet")

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

    def test_changed_lines_count_from_the_last_commit(self):
        with TemporaryProject({"a.txt": b"one\ntwo\nthree\n", ".gitattributes": b"a.txt -diff\n"},
                              git=True) as root:
            git = Git()
            (root / "a.txt").write_bytes(b"ONE\ntwo\nthree\n")
            git.run(root, "add", "a.txt")
            (root / "a.txt").write_bytes(b"ONE\ntwo\nTHREE\nfour\n")
            (root / "new.txt").write_bytes(b"new\n")
            self.assertEqual((git.changed_ranges(root / "a.txt"), git.changed_ranges(root / "new.txt")),
                             ((LineRange(1, 1), LineRange(3, 2)), None),
                             "staged and unstaged changes both count, a file marked -diff still reads as "
                             "text, and an untracked file has no commit to compare with")

    def test_a_repository_with_no_commit_has_nothing_to_compare_with(self):
        with TemporaryProject({"a.txt": b"one\n"}) as root:
            git = Git()
            git.run(root, "init", "-q")
            git.run(root, "add", "a.txt")
            self.assertIsNone(git.changed_ranges(root / "a.txt"), "a staged file with no HEAD compares with "
                                                                    "nothing")

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

    def test_a_repositorys_fsmonitor_program_never_runs(self):
        with TemporaryProject({"a.txt": b"one\n"}, git=True) as root:
            marker = root / "ran.txt"
            (root / "hook.py").write_bytes(f"open({marker.as_posix()!r}, 'w').write('x')\n".encode())
            hook = f'"{Path(sys.executable).as_posix()}" "{(root / "hook.py").as_posix()}"'
            git = Git()
            git.run(root, "config", "core.fsmonitor", hook)
            (root / "a.txt").write_bytes(b"two\n")
            git.root(root)
            git.status(root)
            git.is_tracked(root / "a.txt")
            git.changed_ranges(root / "a.txt")
            self.assertFalse(marker.exists(),
                             "io-guard's git calls run no program a repository's config names")

    def test_a_file_name_is_a_name_and_never_a_pattern(self):
        with TemporaryProject({"i.tsx": b"x\n"}, git=True) as root:
            (root / "[id].tsx").write_bytes(b"y\n")
            self.assertFalse(Git().is_tracked(root / "[id].tsx"),
                             "[id].tsx is untracked, though as a pattern it would match i.tsx")

    def test_a_worktree_rename_parses_from_a_real_status(self):
        with TemporaryProject({"a.txt": b"one\ntwo\nthree\n"}, git=True) as root:
            git = Git()
            (root / "a.txt").rename(root / "b.txt")
            git.run(root, "add", "-N", "b.txt")
            entries = git.status(root).entries
            self.assertEqual({entry.path for entry in entries}, {"b.txt"},
                             "the rename is one entry for b.txt, with no piece of a path left over")

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
