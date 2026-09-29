"""lib.text shows the characters the Read tool hides, and numbers lines as the Read tool does."""
import time
import unicodedata
import unittest

from ioguard.lib.text import INVISIBLE, head, invisible_added, snippet, visible


class HiddenCharactersBecomeMarkers(unittest.TestCase):
    def test_each_hidden_character_has_a_marker(self):
        raw = chr(0xFEFF) + "\tx\r" + chr(0xE0A0) + " y  "
        self.assertEqual(visible(raw), "[BOM][TAB]x[CR][U+E0A0] y[SP][SP]",
                         "a tab, a CR, a BOM, a private-use glyph and trailing spaces each show")

    def test_inner_spaces_stay_spaces(self):
        self.assertEqual(visible("a b"), "a b", "only a space at the end of a line is marked")

    def test_a_long_run_of_spaces_before_text_takes_linear_time(self):
        started = time.perf_counter()
        shown = visible(" " * 100_000 + "x\nend \t \n")
        self.assertEqual((shown.endswith("x\nend[SP][TAB][SP]\n"), time.perf_counter() - started < 0.5),
                         (True, True), "spaces before text stay, and a file's line cannot stall the server")


class LinesAreNumberedAsReadNumbersThem(unittest.TestCase):
    def test_the_lines_around_are_included(self):
        text = "\n".join(f"l{number}" for number in range(1, 13))
        self.assertEqual(snippet(text, 10, 10, 1), " 9| l9\n10| l10\n11| l11",
                         "one line each side, numbered to one width")


class InvisibleCharactersAreNamed(unittest.TestCase):
    def test_a_character_the_write_added_is_named_with_its_first_line(self):
        after = "a\nb" + chr(0x200B) + "\nc" + chr(0xFEFF) + "\nd" + chr(0x200B) + "\n"
        self.assertEqual(invisible_added("a\nb\n", after), ((2, "U+200B"), (3, "U+FEFF")),
                         "each new character once, at the first line that holds it")

    def test_one_already_there_a_leading_bom_and_an_allowed_one_are_not_new(self):
        nbsp, zwsp = chr(0xA0), chr(0x200B)
        self.assertEqual(invisible_added("x" + zwsp + "\n", chr(0xFEFF) + "x" + zwsp + "\ny" + nbsp,
                                         frozenset({"U+00A0"})), (),
                         "a moved character, the file's BOM and an allowed character pass")

    def test_every_format_character_python_knows_is_invisible(self):
        missing = [f"U+{code:04X}" for code in range(0x110000)
                   if unicodedata.category(chr(code)) == "Cf" and not INVISIBLE.match(chr(code))]
        self.assertEqual(missing, [], f"Unicode {unicodedata.unidata_version} category Cf is covered")


class LongTextIsCut(unittest.TestCase):
    def test_the_count_of_what_was_cut_follows(self):
        self.assertEqual((head("abc", 5), head("abcdef", 3)), ("abc", "abc\n[3 more characters]"),
                         "text past the limit ends with the count of what was cut")


if __name__ == "__main__":
    unittest.main()
