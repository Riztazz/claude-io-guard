"""lib.anchors finds where an old_string is, where it nearly is, and the shortest text naming one place."""
import unittest

from ioguard.lib.anchors import blind, closest, deletion_joins, edit_view, find, joins, unique_anchor

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


class ADroppedSpaceJoinsTheTextAfterIt(unittest.TestCase):
    TEXT = "a = f(x.Branch, 1);\nb = f(y.Branch, 2);\nc = g(z.Branch, \n"

    def test_every_match_the_line_goes_on_after_is_joined(self):
        found = joins(self.TEXT, ".Branch, ", ".Branch.ToInt(),", every=True)
        self.assertEqual([(place.line, place.after, place.next) for place in found],
                         [(1, "a = f(x.Branch.ToInt(),1);", "1"), (2, "b = f(y.Branch.ToInt(),2);", "2")],
                         "the third match ends its line, so losing its space joins nothing")

    def test_one_match_counts_only_when_it_is_the_only_one(self):
        self.assertEqual((len(joins(self.TEXT, "x.Branch, ", "x.B,", every=False)),
                          joins(self.TEXT, ".Branch, ", ".B,", every=False)), (1, ()),
                         "the Edit tool refuses a repeated match without replace_all, so nothing joins")

    def test_a_new_string_that_keeps_whitespace_or_is_empty_joins_nothing(self):
        for old, new in ((".Branch, ", ".B, "), (".Branch, ", ".B\t"), (".Branch, ", ""), (" ", "x"),
                         (".Branch,", ".B")):
            with self.subTest(old=old, new=new):
                self.assertEqual(joins(self.TEXT, old, new, every=True), (),
                                 "only a space after text in old_string, missing from new_string, can join")

    def test_a_deletion_that_opens_with_a_line_break_joins_the_lines_around_it(self):
        text = "a\nb\nc\nb"
        found = deletion_joins("a\nb\nc\n", "\nb", "", every=False)
        self.assertEqual([(place.line, place.after) for place in found], [(1, "ac")],
                         "the tool removes the line break after b too, so a meets c")
        self.assertEqual([place.after for place in deletion_joins("a\nb\nc\n", "\nb\n", "", every=False)],
                         ["ac"], "an old_string with both line breaks joins the same two lines")
        for old, new, every in (("b\n", "", False), ("\nb", "x", False), ("\nb", "", False)):
            with self.subTest(old=old, new=new):
                self.assertEqual(deletion_joins(text, old, new, every), (),
                                 "one that opens with text, replaces, or is repeated joins nothing")
        self.assertEqual(len(deletion_joins(text, "\nb", "", every=True)), 1,
                         "with replace_all each match a line break follows counts, and the last has none")
        self.assertEqual(deletion_joins("a\n\nb\n\nc\n", "\nb\n", "", every=False), (),
                         "a join into a blank line leaves every line of text on its own")

    def test_the_joined_line_is_the_last_line_of_a_multi_line_new_string(self):
        found = joins("f(a, b);\n", "a, ", "a,\n  c,", every=False)
        self.assertEqual((found[0].line, found[0].after), (1, "  c,b);"), "the join lands on new's last line")


if __name__ == "__main__":
    unittest.main()
