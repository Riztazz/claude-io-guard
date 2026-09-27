"""lib.text shows the characters the Read tool hides, and numbers lines as the Read tool does."""
import unittest

from ioguard.lib.text import head, snippet, visible


class HiddenCharactersBecomeMarkers(unittest.TestCase):
    def test_each_hidden_character_has_a_marker(self):
        raw = chr(0xFEFF) + "\tx\r" + chr(0xE0A0) + " y  "
        self.assertEqual(visible(raw), "[BOM][TAB]x[CR][U+E0A0] y[SP][SP]",
                         "a tab, a CR, a BOM, a private-use glyph and trailing spaces each show")

    def test_inner_spaces_stay_spaces(self):
        self.assertEqual(visible("a b"), "a b", "only a space at the end of a line is marked")


class LinesAreNumberedAsReadNumbersThem(unittest.TestCase):
    def test_the_lines_around_are_included(self):
        text = "\n".join(f"l{number}" for number in range(1, 13))
        self.assertEqual(snippet(text, 10, 10, 1), " 9| l9\n10| l10\n11| l11",
                         "one line each side, numbered to one width")


class LongTextIsCut(unittest.TestCase):
    def test_the_count_of_what_was_cut_follows(self):
        self.assertEqual((head("abc", 5), head("abcdef", 3)), ("abc", "abc\n[3 more characters]"),
                         "text past the limit ends with the count of what was cut")


if __name__ == "__main__":
    unittest.main()
