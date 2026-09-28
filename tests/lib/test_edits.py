"""A change is placed in the LF view the Edit tool reads, and made in the file's own text: every other ending
stays, new line breaks take the ending named, and a batch is made whole or not at all."""
import unittest

from ioguard.lib import edits
from ioguard.lib.edits import Applied, Change, Missed
from ioguard.lib.profile import Eol


class AChangeLandsInTheFilesOwnText(unittest.TestCase):
    def test_an_lf_view_offset_lands_past_every_crlf_before_it(self):
        text = "a\r\nb\nc\rd\r\ne\r\n"
        view = "a\nb\nc\nd\ne\n"
        start = view.index("d")
        self.assertEqual(edits.replaced(text, start, start + 3, "D\nE", Eol.CRLF), "a\r\nb\nc\rD\r\nE\r\n",
                         "the CRLFs, the LF and the lone CR before the change stay, and the change's own "
                         "break takes CRLF")

    def test_a_new_line_break_takes_the_ending_named(self):
        for eol, expected in ((Eol.CRLF, "x\r\n1\r\n2\r\n"), (Eol.LF, "x\r\n1\n2\r\n"),
                              (Eol.CR, "x\r\n1\r2\r\n")):
            with self.subTest(eol=eol):
                self.assertEqual(edits.replaced("x\r\ny\r\n", 2, 3, "1\n2", eol), expected,
                                 "every break in the new text, and none outside it, takes the ending")


class ABatchIsMadeWholeOrNotAtAll(unittest.TestCase):
    def test_each_change_is_found_in_the_text_the_changes_before_it_left(self):
        made = edits.apply("one\r\ntwo\r\n", [Change("one", "uno"), Change("uno\ntwo", "1\n2\n3")], Eol.CRLF,
                           None)
        self.assertEqual((made.text, made.lines), ("1\r\n2\r\n3\r\n", ((1, 3), (1, 3))),
                         "the second change matches the first one's text, and both cover the lines they made")

    def test_the_lines_of_an_earlier_change_move_with_a_later_one_above_it(self):
        made = edits.apply("a\nb\nc\n", [Change("c", "C"), Change("a\n", "a\nA1\nA2\n")], Eol.LF, None)
        self.assertEqual(made.lines, ((5, 5), (1, 3)), "C moved down two lines, and the result says so")

    def test_the_first_change_that_misses_or_repeats_is_named(self):
        for changes, index, matches in (([Change("a", "b"), Change("zzz", "y")], 1, 0),
                                        ([Change("x", "y")], 0, 2), ([Change("", "y")], 0, 0)):
            with self.subTest(changes=changes):
                missed = edits.apply("a\nx\nx\n", changes, Eol.LF, None)
                self.assertEqual((type(missed), missed.index, len(missed.matches)), (Missed, index, matches),
                                 "Missed names the change and its matches, and nothing is made")
        self.assertEqual(edits.apply("a\nx\n", [Change("a", "b"), Change("q", "y")], Eol.LF, None).text,
                         "b\nx\n", "Missed carries the text the missing change was looked for in")

    def test_new_text_takes_the_indent_style_around_it(self):
        made = edits.apply("{\n\tone;\n\ttwo;\n}\n", [Change("\ttwo;", "  two;\n  three;")], Eol.LF, None)
        self.assertEqual((made.text, made.indented), ("{\n\tone;\n\ttwo;\n\tthree;\n}\n", ((0, "tabs"),)),
                         "spaces become tabs beside tab-indented lines, and Applied names the change")
        self.assertIsInstance(made, Applied, "a batch that matched is Applied")


class AnAppendEndsTheFileAsItEnded(unittest.TestCase):
    def test_the_last_line_break_is_kept_as_the_file_had_it(self):
        for text, expected in (("a\r\n", "a\r\nb\r\n"), ("a", "a\r\nb"), ("", "b\r\n")):
            with self.subTest(text=text):
                self.assertEqual(edits.appended(text, "b\n", Eol.CRLF), expected,
                                 "a last line with no break gets one before the new lines, and none after")

    def test_long_lines_wrap_under_their_first_word(self):
        for line, expected in (("- one two three", "- one two\n  three"),
                               ("\t* one two three", "\t* one two\n\t  three"),
                               ("12. one two six", "12. one two\n    six"),
                               ("plain words here", "plain words\nhere"), ("short", "short"),
                               ("averyveryverylongword x", "averyveryverylongword\nx")):
            with self.subTest(line=line):
                self.assertEqual(edits.wrapped(line, 11), expected,
                                 "a list marker's text hangs under itself, and a long word stays whole")


if __name__ == "__main__":
    unittest.main()
