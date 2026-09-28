"""The journal names the lines a write changed, keeps each added and removed line as a key rather than its
text, and reads back every line it wrote."""
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ioguard.lib import journal

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
k = journal.key


class ChangedLinesAreFoundLineByLine(unittest.TestCase):
    def test_a_replaced_line_names_its_new_line_and_both_keys(self):
        found = journal.changed("a\nb\nc\n", "a\nB\nc\n")
        self.assertEqual(found, journal.Changed(((2, 2),), (k("B"),), (k("b"),)),
                         "a line changed in place is line 2, added as B and removed as b")

    def test_an_inserted_block_names_each_new_line(self):
        found = journal.changed("a\nc\n", "a\nb1\nb2\nc\n")
        self.assertEqual(found, journal.Changed(((2, 3),), (k("b1"), k("b2")), ()),
                         "two lines inserted after a are lines 2 and 3, and nothing was removed")

    def test_a_deleted_line_sits_at_the_line_after_it(self):
        found = journal.changed("a\nb\nc\n", "a\nc\n")
        self.assertEqual(found, journal.Changed(((2, 2),), (), (k("b"),)),
                         "a deletion is placed at the line that now follows it, and names what it removed")

    def test_a_new_file_is_all_added(self):
        self.assertEqual(journal.changed(None, "x\ny\n"), journal.Changed(((1, 2),), (k("x"), k("y")), ()),
                         "with no file before, every line is new")

    def test_line_endings_change_neither_the_lines_nor_the_keys(self):
        self.assertEqual(journal.changed("a\r\nb\r\n", "a\r\nB\r\n"), journal.changed("a\nb\n", "a\nB\n"),
                         "a CRLF file journals as its LF twin, so a key matches git diff's view of the line")

    def test_a_middle_past_the_limit_is_one_change(self):
        before = "".join(f"old {number}\n" for number in range(10))
        after = "".join(f"new {number}\n" for number in range(10))
        with mock.patch.object(journal, "MIDDLE_LINES", 3):
            found = journal.changed(before, after)
        self.assertEqual((found.lines, len(found.added), len(found.removed)), (((1, 10),), 10, 10),
                         "a middle too long to diff line by line is one change, still keyed line by line")

    def test_bytes_that_are_not_utf8_keep_a_key(self):
        text = journal.text_of(b"caf\xe9\n")
        self.assertEqual(journal.key(text), journal.key(journal.text_of(b"caf\xe9")),
                         "a cp1250 line keys the same from a file and from git diff, with no decode error")


class TheJournalFileReadsBack(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-journal-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def entry(self, session: str, tag: str | None) -> journal.Entry:
        return journal.Entry(NOW, session, "C:/project", "C:/project/a.py", "Edit", tag,
                             journal.changed("a\n", "b\n"))

    def test_every_entry_comes_back_as_written(self):
        written = [self.entry("s1", "pass"), self.entry("s2", None)]
        for each in written:
            journal.record(self.home, each)
        self.assertEqual(sorted(journal.entries(self.home), key=lambda entry: entry.session), written,
                         "each session's file holds its entries, tag, lines and keys included")

    def test_a_line_that_cannot_be_read_is_skipped(self):
        journal.record(self.home, self.entry("s1", "pass"))
        path = journal.file_of(self.home, "s1", NOW)
        path.write_bytes(path.read_bytes() + b"{not json\n")
        self.assertEqual(len(list(journal.entries(self.home))), 1, "a torn line costs itself only")


if __name__ == "__main__":
    unittest.main()
