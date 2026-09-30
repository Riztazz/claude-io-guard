"""output reads a shell result: its exit code, its error lines, its mojibake and where a long output was
saved."""
import re
import unittest
from pathlib import Path

from ioguard.lib import output

PATTERNS = {"compiler": re.compile(r"^(?:[^\s:(][^\n(]*\(\d+\)[ \t]*:[ \t]*)?error [A-Z]+\d+:", re.M),
            "exception": re.compile(r"^[A-Z]\w*Error(?::|$)", re.M),
            "tool": re.compile(r"^(?:error|fatal): ", re.M)}


class TheExitCodeAndTheSavedFile(unittest.TestCase):
    def test_the_exit_code_is_read_from_the_first_line_only(self):
        self.assertEqual([output.exit_code(text) for text in ("Exit code 1\nx", "Exit code 127", "boom",
                                                              "x\nExit code 3")],
                         [1, 127, None, None], "Claude Code puts the code on the error's first line")

    def test_the_saved_file_comes_from_persisted_output_path_first(self):
        response = {"stdout": "1\n2\n", "persistedOutputPath": "C:\\a\\tool-results\\b1.txt"}
        self.assertEqual(output.saved_path(response), "C:\\a\\tool-results\\b1.txt",
                         "the response names the file when Claude Code saved the output")

    def test_the_saved_file_comes_from_the_notice_when_no_path_field_came(self):
        stdout = ("<persisted-output>\nOutput too large (41.2KB). Full output saved to: C:\\a\\b 2.txt\n\n"
                  "Preview (first 2KB):\n1\n")
        self.assertEqual(output.saved_path({"stdout": stdout}), "C:\\a\\b 2.txt",
                         "an older release names the file only in its notice")

    def test_an_output_shown_whole_names_no_file(self):
        self.assertIsNone(output.saved_path({"stdout": "all of it"}), "nothing was saved")


class ABackgroundTasksOutputFileIsToldByItsPath(unittest.TestCase):
    def test_only_an_output_file_in_the_sessions_tasks_folder_is_one(self):
        home = "C:/Temp/claude/C--project/"
        for path, expected in ((f"{home}S-1/tasks/b1.output", True), (f"{home}s-1/tasks/b1.output", True),
                               (f"{home}S-2/tasks/b1.output", False), (f"{home}S-1/tasks/b1.txt", False),
                               (f"{home}S-1/scratchpad/b1.output", False),
                               ("C:/project/tasks/b1.output", False)):
            with self.subTest(path=path):
                self.assertEqual(output.is_task_output(Path(path), "S-1"), expected,
                                 "an .output file in the tasks folder of this session's own folder, and "
                                 "no other file")


class ErrorLinesMatchFromTheStartOfALine(unittest.TestCase):
    def test_each_error_line_comes_with_its_number_and_kind(self):
        text = "Building\r\na.cpp(12): error C2065: 'x': undeclared\r\nTraceback\nValueError: bad\n"
        found = output.error_lines(text, PATTERNS)
        self.assertEqual([(line.number, line.kind, line.text) for line in found],
                         [(2, "compiler", "a.cpp(12): error C2065: 'x': undeclared"),
                          (4, "exception", "ValueError: bad")],
                         "the line number counts from 1, and the CR of a CRLF line is dropped")

    def test_a_line_that_only_quotes_an_error_word_raises_nothing(self):
        text = ("Build succeeded. 0 error(s), 2 warning(s)\nErrors: 0\nno errors found\n"
                "LogInit: Display: error count 0\n  // error C2065 is what this avoids\n")
        self.assertEqual(output.error_lines(text, PATTERNS), (),
                         "a summary or a comment that names an error is no error (OUT-7)")

    def test_a_line_two_groups_match_counts_once_for_the_first_group(self):
        patterns = {"first": re.compile(r"^error: ", re.M), "second": re.compile(r"^error", re.M)}
        found = output.error_lines("error: x\n", patterns)
        self.assertEqual([(line.number, line.kind) for line in found], [(1, "first")],
                         "the group named first wins")

    def test_the_last_line_without_a_newline_is_read(self):
        self.assertEqual([line.text for line in output.error_lines("ok\nfatal: gone", PATTERNS)],
                         ["fatal: gone"], "the text may end without a line break")


class MojibakeIsFound(unittest.TestCase):
    def test_utf8_read_in_cp1252_is_found_with_what_it_meant(self):
        shown = "caf\u00c3\u00a9 \u00e2\u2020\u2019 done"
        found = output.mojibake(shown, ["cp1252"])
        self.assertEqual((found.garbled, found.example, found.meant, found.replaced),
                         (2, "\u00c3\u00a9", "\u00e9", 0), "each run decodes back to the character it was")

    def test_utf8_read_in_cp1250_is_found(self):
        found = output.mojibake("B\u0139\u201a\u00c4\u2026d", ["cp1252", "cp1250"])
        self.assertEqual((found.garbled, found.meant), (1, "\u0142\u0105"),
                         "a Polish console shows the UTF-8 of l-stroke and a-ogonek this way")

    def test_replacement_characters_are_counted(self):
        self.assertEqual(output.mojibake("Contract \ufffd one \ufffd", ["cp1252"]).replaced, 2,
                         "each U+FFFD stands for bytes that were not UTF-8")

    def test_real_text_with_accents_is_left_alone(self):
        for text in ("Gr\u00f6\u00dfe", "na\u00efve caf\u00e9", "Za\u017c\u00f3\u0142\u0107", "\u00a9 2026"):
            with self.subTest(text=text):
                found = output.mojibake(text, ["cp1252", "cp1250"])
                self.assertEqual((found.garbled, found.replaced), (0, 0), "these bytes are what they say")


class TheExcerptKeepsTheEndsAndTheErrors(unittest.TestCase):
    def test_head_marked_lines_and_tail_are_numbered_with_the_gaps_said(self):
        text = "".join(f"line {n}\n" for n in range(1, 101))
        marked = [output.ErrorLine(50, "compiler", "line 50")]
        shown = output.excerpt(text, 2, 2, marked, 100).split("\n")
        self.assertEqual(shown, ["  1| line 1", "  2| line 2", "[47 lines left out, 3 to 49]", " 50| line 50",
                                 "[48 lines left out, 51 to 98]", " 99| line 99", "100| line 100"],
                         "the model sees where each shown line sits in the whole output")

    def test_a_short_text_is_shown_whole(self):
        self.assertEqual(output.excerpt("a\r\nb\r\n", 20, 20, [], 100), "1| a\n2| b",
                         "no gap, and the CR of each line is dropped")

    def test_a_long_line_is_cut_with_the_count_of_what_was_cut(self):
        self.assertEqual(output.excerpt("x" * 12, 1, 1, [], 5), "1| xxxxx [7 more characters]",
                         "one huge line cannot fill the whole view")


if __name__ == "__main__":
    unittest.main()
