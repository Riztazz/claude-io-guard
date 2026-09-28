"""lib.drift compares a file after a write with the file before it and with the text the call asked for."""
import unittest

from ioguard.lib.drift import changed_lines, drift, edited, frontmatter_end, restored, would_collapse
from ioguard.lib.profile import Bom, Eol, profile

BOM = b"\xef\xbb\xbf"


class ProfilesShowWhatChanged(unittest.TestCase):
    def test_an_ending_style_change_is_one_fact(self):
        found = drift(profile(b"a\r\nb\r\n"), profile(b"a\nb\n"))
        self.assertEqual((found.eol, found.bom), ((Eol.CRLF, Eol.LF), None),
                         "CRLF became LF, and no BOM moved")

    def test_mixed_before_or_no_ending_after_is_no_style_change(self):
        for before, after in ((b"a\r\nb\n", b"a\nb\n"), (b"a\r\n", b"a")):
            with self.subTest(before=before, after=after):
                self.assertIsNone(drift(profile(before), profile(after)).eol,
                                  "a file with no single style, or no line left to end, has no style to lose")

    def test_a_lost_bom_and_added_bytes_are_counted(self):
        before = profile(BOM + b"a\n")
        after = profile("a\x00\x01".encode() + chr(0xFFFD).encode() + chr(0x2192).encode() + b"\n")
        found = drift(before, after)
        self.assertEqual((found.bom, found.nul, found.control, found.replacement, found.invalid),
                         ((Bom.UTF8, Bom.NONE), 1, 1, 1, False), "each odd byte the write added is counted")
        self.assertEqual(found.non_ascii, 2, "U+FFFD and the arrow are two non-ASCII characters")

    def test_utf8_that_stops_decoding_is_invalid(self):
        self.assertTrue(drift(profile(b"caf\xc3\xa9\n"), profile(b"caf\xe9\n")).invalid,
                        "valid UTF-8 before and a cp1252 byte after is an encoding change")


class AnEditIsAppliedAsTheToolReadsTheFile(unittest.TestCase):
    def test_crlf_and_a_bom_read_as_lf(self):
        found = edited(chr(0xFEFF) + "x\r\na\r\nb\r\n", "a\nb", "a\nc", False)
        self.assertEqual((found.text, found.lines), ("x\na\nc\n", frozenset({2, 3})),
                         "the tool matches old_string with CRLF read as LF, and new_string covers lines 2 "
                         "and 3")

    def test_a_missing_or_repeated_anchor_has_no_expected_text(self):
        for old, replace_all in (("z", False), ("a", False), ("", True)):
            with self.subTest(old=old):
                self.assertIsNone(edited("a\na\n", old, "b", replace_all),
                                  "the tool failed or matched another way, so no text is expected")

    def test_replace_all_replaces_every_match(self):
        found = edited("a\nz\na\n", "a", "b\nb", True)
        self.assertEqual((found.text, found.lines), ("b\nb\nz\nb\nb\n", frozenset({1, 2, 4, 5})),
                         "replace_all changes each match, and each covers its own lines")


class ChangedLinesAreCountedFromOne(unittest.TestCase):
    def test_changed_inserted_and_removed_lines(self):
        cases = {"same": ("a\nb\nc\n", "a\nb\nc\n", ()), "changed": ("a\nb\nc\n", "a\nX\nc\n", (2,)),
                 "inserted": ("a\nc\n", "a\nb\nc\n", (2,)), "removed": ("a\nb\nc\n", "a\nc\n", (2,)),
                 "appended": ("a\n", "a\nb\n", (2,)), "endings": ("a\nb\n", "a\r\nb\r\n", ())}
        for name, (expected, actual, lines) in cases.items():
            with self.subTest(name):
                self.assertEqual(changed_lines(expected, actual), lines,
                                 "only lines whose text differs count, never their endings")


class FrontmatterEndsAtItsSecondRule(unittest.TestCase):
    def test_the_last_line_of_a_leading_block_or_zero(self):
        cases = {"block": ("---\na: 1\n---\nbody\n", 3), "crlf": ("---\r\na: 1\r\n---\r\n", 3),
                 "unclosed": ("---\na: 1\n", 0), "not first": ("body\n---\na\n---\n", 0), "empty": ("", 0)}
        for name, (text, end) in cases.items():
            with self.subTest(name):
                self.assertEqual(frontmatter_end(text), end, "a --- line opens it and the next one closes it")


class ACollapseIsUnderThePercent(unittest.TestCase):
    def test_both_sides_of_half(self):
        self.assertEqual([would_collapse(100, size, 50) for size in (0, 49, 50, 100)],
                         [True, True, False, False],
                         "a file under half the bytes the call should leave has collapsed")

    def test_nothing_expected_never_collapses(self):
        self.assertFalse(would_collapse(0, 0, 50), "an empty file asked for is not a collapse")


class RepairWritesTheEndingsAndBomBack(unittest.TestCase):
    def test_lf_back_to_crlf_with_a_bom(self):
        self.assertEqual(restored(b"a\nb\n", Eol.CRLF, Bom.UTF8), BOM + b"a\r\nb\r\n",
                         "the file's own endings and BOM go back on")

    def test_a_bom_alone_leaves_every_ending_as_it_is(self):
        self.assertEqual(restored(b"a\nb\rc\r\n", None, Bom.UTF8), BOM + b"a\nb\rc\r\n",
                         "with no ending named, a lone CR and a mixed ending stay")

    def test_bytes_that_are_not_utf8_are_not_repaired(self):
        self.assertIsNone(restored(b"caf\xe9\n", Eol.CRLF, Bom.NONE),
                          "a legacy code page is never re-encoded")


if __name__ == "__main__":
    unittest.main()
