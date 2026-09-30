"""New text takes the indent style of the lines where it lands, tabs or spaces, when the two differ."""
import unittest

from ioguard.lib import indent
from ioguard.lib.profile import IndentKind


class NewTextTakesTheIndentAroundIt(unittest.TestCase):
    def test_the_style_of_indented_lines_is_named(self):
        for text, style in (("\ta\n\tb", IndentKind.TABS), ("    a\n  b", IndentKind.SPACES),
                            ("\ta\n    b", IndentKind.MIXED), ("a\n b", IndentKind.NONE)):
            with self.subTest(text=text):
                self.assertEqual(indent.style(text), style, "a lone space is not an indent")

    def test_tabs_and_spaces_convert_only_when_they_differ(self):
        for new, near, width, expected in (("    a\n        b", "\tx", None, "\ta\n\t\tb"),
                                           ("\ta", "  x\n  y", None, "  a"), ("\ta", "    x", 2, "  a"),
                                           ("\ta", "\tx", None, None), ("\ta\n  b", "  x", None, None)):
            with self.subTest(new=new, near=near):
                self.assertEqual(indent.fitted(new, near, width), expected,
                                 "new text converts to the style around it, with the file's step or the "
                                 "spaced side's own")

    def test_the_lines_around_a_place_reach_three_either_side(self):
        text = "\n".join(str(number) for number in range(1, 11))
        self.assertEqual(indent.around(text, 5, 6), "2\n3\n4\n5\n6\n7\n8\n9", "three lines above and below")
        self.assertEqual(indent.around(text, 1, 1), "1\n2\n3\n4", "cut at the start of the text")


if __name__ == "__main__":
    unittest.main()
