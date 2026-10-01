"""profile reads a file's endings, BOM, encoding, indent, shape and odd bytes from its raw bytes, and
target_profile gives the convention a new file takes."""
import time
import unittest

from ioguard.lib.profile import (Bom, Eol, IndentKind, convert_eol, legacy_guess, profile, target_profile,
                                 with_bom, with_final_newline)
from tests.support.fixtures import FIXTURES_DIR


def of(name: str):
    return profile((FIXTURES_DIR / name).read_bytes())


class EveryFixtureProfilesAsWritten(unittest.TestCase):
    def test_line_endings(self):
        cases = {"crlf.txt": (Eol.CRLF, (3, 0, 0)), "lf.txt": (Eol.LF, (0, 3, 0)),
                 "mixed.txt": (Eol.MIXED, (2, 2, 0)), "lone-cr.txt": (Eol.CRLF, (2, 0, 1)),
                 "bom-crlf.txt": (Eol.CRLF, (2, 0, 0)), "empty.txt": (Eol.NONE, (0, 0, 0))}
        for name, (eol, counts) in cases.items():
            with self.subTest(fixture=name):
                found = of(name)
                ending = found.eol_counts
                self.assertEqual((found.eol, (ending.crlf, ending.lf, ending.cr)), (eol, counts),
                                 "the style comes from CRLF and LF, and a lone CR is counted")

    def test_bom_and_encoding(self):
        cases = {"bom-crlf.txt": (Bom.UTF8, True, None, None), "lf.txt": (Bom.NONE, True, None, None),
                 "cp1250.txt": (Bom.NONE, False, 2, "cp1250")}
        for name, expected in cases.items():
            with self.subTest(fixture=name):
                found = of(name)
                self.assertEqual((found.bom, found.encoding.utf8, found.encoding.first_invalid,
                                  found.encoding.guess), expected,
                                 "a BOM is named, and invalid UTF-8 gets its first offset and a code page")

    def test_shape(self):
        cases = {"no-final-newline.txt": (False, 2), "lf.txt": (True, 3), "empty.txt": (False, 0),
                 "lone-cr.txt": (True, 3)}
        for name, expected in cases.items():
            with self.subTest(fixture=name):
                found = of(name)
                self.assertEqual((found.final_newline, found.line_count), expected,
                                 "a last line without an ending still counts")

    def test_indent(self):
        cases = {"indent-tab.cpp": (IndentKind.TABS, None, 2, 0),
                 "indent-space.cpp": (IndentKind.SPACES, 4, 0, 2),
                 "indent-both.cpp": (IndentKind.MIXED, 4, 1, 1), "lf.txt": (IndentKind.NONE, None, 0, 0)}
        for name, expected in cases.items():
            with self.subTest(fixture=name):
                indent = of(name).indent
                self.assertEqual((indent.kind, indent.width, indent.tab_lines, indent.space_lines), expected,
                                 "tabs, spaces and their width come from the lines' leading whitespace")

    def test_the_step_is_the_commonest_rise_past_aligned_continuation_lines(self):
        cases = {
            "aligned under a bracket": (b"PROBES = {\n    \"a\": Probe(0, allowed=(\"Read\",),\n"
                                        b"                 check=(\"a\",),\n                 max_turns=8,\n"
                                        b"                 setup={}),\n    \"b\": Probe(1),\n}\n", 4),
            "a message under a call": (b"class T:\n    def t(self):\n        self.assertEqual(a, b,\n"
                                       b"                         \"why\")\n        self.x(c)\n", 4),
            "two-space yaml": (b"jobs:\n  test:\n    runs-on: x\n    steps:\n      - run: y\n", 2)}
        for name, (data, width) in cases.items():
            with self.subTest(name):
                self.assertEqual(profile(data).indent.width, width,
                                 "a block rises by the step, and an aligned line once per statement")

    def test_odd_bytes_and_the_binary_sniff(self):
        nul, private = of("nul-byte.txt"), of("private-use.txt")
        self.assertEqual((nul.counts.nul, nul.binary), (1, True), "a NUL in the first 8 KB marks it binary")
        self.assertEqual((private.counts.private_use, private.counts.non_ascii, private.binary),
                         (1, 1, False), "a private-use glyph is counted, and it is one non-ASCII character")
        high = profile(("a" + chr(0xF8FF) + chr(0xF0001) + chr(0xE9) + "\n").encode("utf-8"))
        self.assertEqual((high.counts.private_use, high.counts.non_ascii), (2, 3),
                         "U+F8FF and the supplementary private-use plane count too, and e-acute does not")

    def test_the_large_fixture_counts_every_line(self):
        found = of("large-300k.txt")
        self.assertEqual((found.eol, found.line_count, found.final_newline),
                         (Eol.LF, (FIXTURES_DIR / "large-300k.txt").read_bytes().count(b"\n"), True),
                         "300 KB of LF lines count to the last one")


class OtherBytes(unittest.TestCase):
    def test_utf16_reads_from_its_text(self):
        found = profile(b"\xff\xfe" + "one\r\ntwo\r\n".encode("utf-16-le"))
        self.assertEqual((found.bom, found.eol, found.line_count, found.binary, found.counts.nul),
                         (Bom.UTF16_LE, Eol.CRLF, 2, False, 0),
                         "UTF-16's NUL bytes are part of its characters")

    def test_trailing_whitespace_and_control_bytes_are_counted(self):
        found = profile(b"a \r\nb\t\nc\x07\n")
        self.assertEqual((found.counts.trailing_ws_lines, found.counts.c0), (2, 1),
                         "a space or tab before an ending counts once per line, and BEL is a control byte")

    def test_a_cp1252_text_is_told_from_cp1250(self):
        western = "caf" + chr(0xE9) + " na" + chr(0xEF) + "ve\n"
        self.assertEqual(profile(western.encode("cp1252")).encoding.guess, "cp1252",
                         "Western accents read as cp1252")


class TheLineAndTheWarnings(unittest.TestCase):
    def test_the_line_names_each_convention(self):
        cases = {"bom-crlf.txt": "CRLF, BOM, UTF-8, 2 lines",
                 "indent-space.cpp": "LF, UTF-8, 4 spaces, 5 lines",
                 "cp1250.txt": "CRLF, not UTF-8, likely cp1250, 1 line", "nul-byte.txt": "binary, 13 bytes"}
        for name, line in cases.items():
            with self.subTest(fixture=name):
                self.assertEqual(of(name).line(), line, "one line says what a write must keep")

    def test_warnings_name_what_a_write_can_break(self):
        cases = {"mixed.txt": "mixes line endings", "lone-cr.txt": "lone CR", "cp1250.txt": "not valid UTF-8",
                 "nul-byte.txt": "NUL bytes", "private-use.txt": "private-use glyphs"}
        for name, words in cases.items():
            with self.subTest(fixture=name):
                self.assertTrue(any(words in warning for warning in of(name).warnings()),
                                f"{name} is warned about")
        self.assertEqual(of("crlf.txt").warnings(), (), "a clean file has no warning")

    def test_a_mixed_file_knows_its_dominant_ending(self):
        self.assertEqual(profile(b"a\r\nb\r\nc\n").eol_counts.dominant, Eol.CRLF, "two CRLF outweigh one LF")

    def test_a_new_line_takes_the_files_own_ending(self):
        for data, eol in ((b"a\r\n", Eol.CRLF), (b"a\rb\r", Eol.CR), (b"a\nb\r\nc\n", Eol.LF),
                          (b"a", Eol.LF)):
            with self.subTest(data=data):
                self.assertEqual(profile(data).new_eol, eol,
                                 "the file's ending, the one most lines use when mixed, and LF with none yet")

    def test_the_codec_reads_the_bytes_whole(self):
        cases = {"bom-crlf.txt": "utf-8", "cp1250.txt": "cp1250", "lf.txt": "utf-8"}
        for name, codec in cases.items():
            with self.subTest(fixture=name):
                self.assertEqual(of(name).codec, codec, "UTF-8, or the code page the bytes suggest")
        utf16 = profile(b"\xff\xfe" + "a\n".encode("utf-16-le"))
        self.assertEqual((utf16.codec, (b"\xff\xfe" + "a\n".encode("utf-16-le")).decode(utf16.codec)),
                         ("utf-16-le", chr(0xFEFF) + "a\n"), "UTF-16 by its BOM, which reads as U+FEFF")


class ANewFilesProfile(unittest.TestCase):
    def test_editorconfig_wins_then_gitattributes_then_siblings(self):
        siblings = [of("lf.txt"), of("lf.txt"), of("crlf.txt")]
        self.assertEqual(target_profile(siblings, {"end_of_line": "crlf"}, {"eol": "lf"}).eol, Eol.CRLF,
                         ".editorconfig decides first")
        self.assertEqual(target_profile(siblings, {}, {"eol": "crlf"}).eol, Eol.CRLF, "then .gitattributes")
        self.assertEqual(target_profile(siblings, {}, {}).eol, Eol.LF, "then the siblings' majority")

    def test_bom_indent_and_final_newline(self):
        siblings = [of("bom-crlf.txt"), of("indent-space.cpp"), of("indent-space.cpp")]
        found = target_profile(siblings, {}, {})
        self.assertEqual((found.bom, found.indent.kind, found.indent.width, found.final_newline),
                         (Bom.NONE, IndentKind.SPACES, 4, True), "each property follows most siblings")
        chosen = target_profile(siblings, {"charset": "utf-8-bom", "indent_style": "tab",
                                           "insert_final_newline": "false"}, {})
        self.assertEqual((chosen.bom, chosen.indent.kind, chosen.final_newline),
                         (Bom.UTF8, IndentKind.TABS, False),
                         ".editorconfig's charset, indent_style and insert_final_newline decide")

    def test_an_indent_size_that_is_not_ascii_digits_names_no_width(self):
        for size in (chr(0xB2), chr(0x0664), "tab", ""):
            with self.subTest(indent_size=ascii(size)):
                found = target_profile([], {"indent_style": "space", "indent_size": size}, {})
                self.assertEqual((found.indent.kind, found.indent.width), (IndentKind.SPACES, None),
                                 "a superscript two or an Arabic-Indic digit is not a width io-guard reads")


class ConvertingText(unittest.TestCase):
    def test_endings_bom_and_final_newline(self):
        self.assertEqual(convert_eol("a\r\nb\nc\rd", Eol.CRLF), "a\r\nb\r\nc\rd",
                         "every ending becomes CRLF, and a lone CR, which ends no line, stays as it is")
        self.assertEqual(convert_eol("a\rb\r\nc\nd", Eol.LF), "a\rb\nc\nd",
                         "in an LF file too the lone CR stays")
        self.assertEqual(convert_eol("a\r\nb\nc\rd", Eol.CR), "a\rb\rc\rd", "in a CR file every ending is CR")
        self.assertEqual(convert_eol("a\nb", Eol.MIXED), "a\nb", "a mixed target changes nothing")
        bom = chr(0xFEFF)
        self.assertEqual((with_bom("x", Bom.UTF8), with_bom(bom + "x", Bom.NONE)), (bom + "x", "x"),
                         "the BOM is added or removed to match")
        added = with_final_newline("a", True, Eol.CRLF)
        removed = with_final_newline("a\r\n\r\n", False, Eol.CRLF)
        self.assertEqual((added, removed), ("a\r\n", "a\r\n"),
                         "one ending is added, or exactly one taken off")


class Speed(unittest.TestCase):
    def test_a_megabyte_profiles_well_inside_its_budget(self):
        data = b"".join(b"\tline %06d with some text in it\r\n" % number for number in range(30000))[:1 << 20]
        started = time.perf_counter()
        profile(data)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.5,
                        "the budget is 20 ms, and this bound catches only a pathological slowdown")

    def test_eight_megabytes_of_high_bytes_get_their_code_page_without_a_loop_in_python(self):
        data = bytes(range(0x80, 0x100)) * (8 * 1024 * 1024 // 128)
        started = time.perf_counter()
        guess = legacy_guess(data)
        elapsed = time.perf_counter() - started
        self.assertEqual(guess, "cp1252", "12 of 128 high bytes are Central European letters, under a third")
        self.assertLess(elapsed, 0.1,
                        "a large image is mostly high bytes, and a loop in Python takes 0.4 s on 8 MB")


if __name__ == "__main__":
    unittest.main()
