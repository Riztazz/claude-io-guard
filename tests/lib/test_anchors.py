"""lib.anchors finds where an old_string is, where it nearly is, and the shortest text naming one place."""
import unittest

from ioguard.lib.anchors import blind, closest, edit_view, find, unique_anchor

TABS = "void f()\n{\n\tint a = 1;\n\tint b = 2;\n}\n"


class FindCountsAsTheEditToolCounts(unittest.TestCase):
    def test_every_place_left_to_right_with_its_lines(self):
        found = find("x\ny\nx\n", "x")
        self.assertEqual([(match.first_line, match.last_line) for match in found], [(1, 1), (3, 3)],
                         "each place and its lines, counted from 1")

    def test_an_empty_anchor_is_nowhere(self):
        self.assertEqual(find("x\n", ""), (), "an empty old_string names no place")

    def test_the_edit_view_reads_every_ending_as_lf(self):
        self.assertEqual(edit_view("a\r\nb\rc\nd"), "a\nb\nc\nd", "CRLF and a lone CR each become one LF")


class WhitespaceIsIgnoredFirst(unittest.TestCase):
    def test_spaces_for_a_tab_still_match_and_take_the_files_indent(self):
        found = closest(TABS, "    int b = 2;")
        self.assertEqual((len(found), found[0].exact, found[0].text, found[0].match.first_line),
                         (1, True, "\tint b = 2;", 4),
                         "the file's own text, tab included, is the corrected old_string")

    def test_an_indented_anchor_never_matches_the_end_of_a_longer_word(self):
        self.assertEqual(blind("barfoo();\n", "    foo();"), (),
                         "an old_string that starts with an indent starts a line")

    def test_trailing_spaces_in_the_anchor_take_the_files_own(self):
        self.assertEqual(closest("x = 1  \ny\n", "x = 1 ")[0].text, "x = 1  ",
                         "the match takes the trailing spaces the file has")

    def test_a_multi_line_anchor_with_other_indent_matches(self):
        found = closest(TABS, "{\n    int a = 1;\n    int b = 2;\n}")
        self.assertEqual((found[0].exact, found[0].match.first_line, found[0].match.last_line), (True, 2, 5),
                         "indent that differs on every line still matches")


class TheNearestLinesComeNext(unittest.TestCase):
    def test_a_near_miss_names_its_lines_and_score(self):
        text = "".join(f"line {number}\n" for number in range(40)) + "\tresult = compute(alpha, beta);\n"
        found = closest(text, "result = compute(alpha, gamma);")
        self.assertEqual((found[0].exact, found[0].match.first_line), (False, 41),
                         "the line most like old_string is offered first")
        self.assertGreater(found[0].score, 0.8, "a one-word difference scores high")

    def test_nothing_alike_offers_nothing(self):
        self.assertEqual(closest(TABS, "completely unrelated text"), (), "no line comes close")


class AUniqueAnchorGrowsByWholeLines(unittest.TestCase):
    def test_the_line_below_then_above_until_one_place(self):
        text = "a\nx\nb\nx\nc\n"
        self.assertEqual(unique_anchor(text, find(text, "x")[1]), "x\nc",
                         "the line below the second x makes it unique")


if __name__ == "__main__":
    unittest.main()
