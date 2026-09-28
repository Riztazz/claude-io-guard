"""hunks reads one file's git diff -U0 into hunks, writes a patch of the chosen ones byte for byte, and tells
whether a hunk is a task's from the journal's line keys."""
import unittest

from ioguard.lib import hunks
from ioguard.lib.journal import key

DIFF = (b"diff --git a/a.txt b/a.txt\nindex 1..2 100644\n--- a/a.txt\n+++ b/a.txt\n"
        b"@@ -3 +3 @@\n-line 3\r\n+LINE 3\r\n"
        b"@@ -9,0 +10,2 @@ context\n+new 10\n+}\n"
        b"@@ -20 +21,0 @@\n-gone\n\\ No newline at end of file\n")


class ADiffBecomesHunks(unittest.TestCase):
    def test_each_hunk_keeps_its_counts_lines_and_bytes(self):
        diff = hunks.parse(DIFF)
        self.assertEqual([hunk.lines() for hunk in diff.hunks], [(3, 3), (10, 11), (22, 22)],
                         "a change, an insertion of two lines, and a deletion placed after line 21")
        self.assertEqual(diff.hunks[0].body, (b"-line 3\r\n", b"+LINE 3\r\n"), "CRLF stays in the bytes")
        self.assertIn(b"\\ No newline", diff.hunks[2].body[-1], "the no-newline note stays with its hunk")

    def test_a_patch_of_chosen_hunks_is_the_head_and_those_hunks_byte_for_byte(self):
        diff = hunks.parse(DIFF)
        self.assertEqual(hunks.patch(diff, diff.hunks), DIFF, "all hunks give back the diff as git wrote it")
        self.assertNotIn(b"new 10", hunks.patch(diff, [diff.hunks[0]]), "a hunk left out is not in the patch")

    def test_no_change_and_a_binary_file_are_told_apart(self):
        self.assertIsNone(hunks.parse(b""), "an empty diff is no change")
        binary = hunks.parse(b"diff --git a/x.bin b/x.bin\nBinary files a/x.bin and b/x.bin differ\n")
        self.assertEqual((binary.binary, binary.hunks), (True, ()), "a binary file has no hunks to stage")

    def test_a_range_meets_the_hunks_it_touches(self):
        insertion = hunks.parse(DIFF).hunks[1]
        self.assertEqual([insertion.meets(first, last) for first, last in ((1, 9), (11, 11), (12, 20))],
                         [False, True, False], "lines 10 and 11 are the insertion's")


class AHunkBelongsToATaskByItsLines(unittest.TestCase):
    def test_a_hunk_whose_telling_lines_are_all_the_tasks_is_the_tasks(self):
        insertion = hunks.parse(DIFF).hunks[1]
        found = hunks.owned(insertion, {key("new 10")}, set())
        self.assertEqual((found.mine, found.mixed), (True, False),
                         "the brace says nothing, and new 10 is the task's, so the hunk is")

    def test_a_hunk_with_some_of_the_tasks_lines_is_mixed(self):
        change = hunks.parse(DIFF).hunks[0]
        found = hunks.owned(change, {key("LINE 3")}, set())
        self.assertEqual((found.mine, found.mixed), (False, True),
                         "the task added LINE 3 but did not remove line 3, so another write is in the hunk")

    def test_a_hunk_of_only_braces_counts_its_braces(self):
        braces = hunks.parse(b"diff --git a/a b/a\n@@ -1,0 +2 @@\n+}\n").hunks[0]
        judged = (hunks.owned(braces, {key("}")}, set()).mine, hunks.owned(braces, set(), set()).mine)
        self.assertEqual(judged, (True, False),
                         "a hunk that holds nothing but a brace is judged by the brace")


if __name__ == "__main__":
    unittest.main()
