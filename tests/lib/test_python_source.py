"""lib.python_source reports what stops a Python program before it runs, without running it."""
import unittest

from ioguard.lib import python_source


class CompilingAProgramsText(unittest.TestCase):
    def test_a_syntax_error_names_its_line_and_text(self):
        report = python_source.compile_report("x = 1\nprint('a'\n")
        self.assertEqual((report.error.line, report.error.text, report.warnings), (2, "print('a'", ()),
                         "the error carries its line number and that line as written")

    def test_a_windows_path_in_a_plain_string_is_an_error(self):
        report = python_source.compile_report('p = "C:\\Users\\me"\n')
        self.assertIn("unicodeescape", report.error.message, "a \\U in a plain string cannot compile")

    def test_an_invalid_escape_is_a_warning(self):
        report = python_source.compile_report('import re\nre.compile("\\d")\n')
        self.assertEqual((report.error, [problem.line for problem in report.warnings]), (None, [2]),
                         "the program compiles, and the invalid escape is reported on its line")

    def test_a_clean_program_reports_nothing_and_a_nul_is_an_error_with_no_line(self):
        self.assertEqual(python_source.compile_report("print(1)\n"), python_source.CompileReport(None, ()),
                         "a program that compiles cleanly reports nothing")
        self.assertIsNone(python_source.compile_report("print(1)\0\n").error.line,
                          "Python refuses a NUL byte anywhere, so the error names no line")


if __name__ == "__main__":
    unittest.main()
