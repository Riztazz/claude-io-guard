"""A change is placed in the LF view the Edit tool reads, and made in the file's own text: every other ending
stays, new line breaks take the ending named, and a batch is made whole or not at all."""
import unittest

from ioguard.lib import edits
from ioguard.lib.edits import Applied, Change, Missed
from ioguard.lib.profile import Eol, IndentKind


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
        self.assertEqual((made.text, made.indented),
                         ("{\n\tone;\n\ttwo;\n\tthree;\n}\n", ((0, IndentKind.TABS),)),
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


class AFormattersOutputKeepsTheFilesEndings(unittest.TestCase):
    def test_only_the_lines_the_formatter_changed_take_the_new_ending(self):
        text = "int  a=1;\r\nvoid f(){y();}\r\nint  b=2;\n"
        formatted = "int  a=1;\nvoid f() {\n  y();\n}\nint  b=2;\n"
        carried = edits.carried(text, formatted, Eol.CRLF)
        self.assertEqual((carried.text, carried.lines),
                         ("int  a=1;\r\nvoid f() {\r\n  y();\r\n}\r\nint  b=2;\n", ((2, 4),)),
                         "BYT-3: a formatter that writes LF leaves a CRLF file CRLF, and the LF line it did "
                         "not touch keeps its LF")

    def test_a_last_line_keeps_or_gains_its_break_as_the_formatter_left_it(self):
        for text, formatted, expected in (("a\r\nb", "a\nb", "a\r\nb"), ("a\r\nb  ;", "a\nb;", "a\r\nb;"),
                                          ("a\r\nb  ;", "a\nb;\n", "a\r\nb;\r\n")):
            with self.subTest(text=text, formatted=formatted):
                self.assertEqual(edits.carried(text, formatted, Eol.CRLF).text, expected,
                                 "an untouched last line keeps its missing break, and a changed one ends as "
                                 "the formatter ended it")

    def test_removed_lines_are_placed_at_the_line_above(self):
        carried = edits.carried("a\n\n\n\nb\n", "a\n\nb\n", Eol.LF)
        self.assertEqual((carried.text, carried.lines), ("a\n\nb\n", ((2, 2),)),
                         "two blank lines removed after line 2 are reported at line 2")

    def test_a_change_away_from_the_lines_asked_stays_as_it_was(self):
        text = "namespace n {\nint  a;\nint  b;\n\nint  c;\n}\n"
        formatted = "namespace n {\nint a;\nint b;\n\nint c;\n} // namespace n\n"
        carried = edits.carried(text, formatted, Eol.LF, within=[(2, 2)])
        self.assertEqual((carried.text, carried.lines, carried.left),
                         ("namespace n {\nint a;\nint b;\n\nint  c;\n}\n", ((2, 3),), ((5, 6),)),
                         "BYT-12: a run that meets line 2 lands whole, and the far run, a namespace closer "
                         "included, stays as the file had it")

    def test_an_insertion_meets_the_lines_on_either_side_of_it(self):
        for within, landed in (([(1, 1)], True), ([(2, 2)], True), ([(3, 3)], False)):
            with self.subTest(within=within):
                carried = edits.carried("a\nb\nc\n", "a\nNEW\nb\nc\n", Eol.LF, within=within)
                self.assertEqual(carried.text == "a\nNEW\nb\nc\n", landed,
                                 "a line added between lines 1 and 2 meets a range on either of them")

    def test_a_formatter_that_writes_crlf_is_read_line_for_line(self):
        self.assertEqual(edits.carried("x=1\ny\n", "x = 1\r\ny\r\n", Eol.LF).text, "x = 1\ny\n",
                         "a CRLF from the formatter is a line break, and the file's LF wins")


if __name__ == "__main__":
    unittest.main()
