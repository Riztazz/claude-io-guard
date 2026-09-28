"""lib.commands checks the shape of the user's verify and format commands, finds the one for a file, and fills
it in for the file and its line ranges."""
import unittest
from pathlib import Path

from ioguard.lib.commands import (CLANG_FORMAT, FORMAT_DEFAULT, command_for, filled, format_problem,
                                  verify_problem)
from ioguard.lib.platform import Platform

WINDOWS = Platform("win32", True)
PY = ["python", "-m", "py_compile", "{file}"]
LINT = ["ruff", "check", "{file}"]
BLACK = ["black", "-q", "--line-ranges={first}-{last}", "-"]
HERE = Path.cwd().anchor + "work/app"      # a project root that is absolute on the host running the test


class TheShapeIsChecked(unittest.TestCase):
    def test_good_values_pass(self):
        for value in ({}, {".py": PY}, {".py": PY, HERE: {".PY": LINT}}):
            with self.subTest(value=value):
                self.assertIsNone(verify_problem(value), "extensions and absolute project roots are the keys")

    def test_each_mistake_is_named(self):
        cases = {"no placeholder": ({".py": ["python", "-m", "py_compile"]}, "{file}"),
                 "one string": ({".py": "python -m py_compile {file}"}, "list of strings"),
                 "bad key": ({"py": PY}, "neither a file extension"),
                 "relative root": ({"work/app": {".py": PY}}, "absolute project folder"),
                 "project not an object": ({HERE: PY}, "object of extensions"),
                 "bad project command": ({HERE: {".py": []}}, "list of strings")}
        for name, (value, words) in cases.items():
            with self.subTest(name):
                self.assertIn(words, verify_problem(value), "the message says what to fix")

    def test_a_format_command_holds_both_ends_of_a_range_in_one_argument(self):
        self.assertIsNone(format_problem(FORMAT_DEFAULT), "the default clang-format commands pass")
        self.assertIsNone(format_problem({".py": BLACK, HERE: {".cpp": CLANG_FORMAT}}),
                          "any program that takes a line range on its command line passes")
        for command in (["black", "-"], ["tool", "--from={first}", "--to={last}"]):
            with self.subTest(command=command):
                self.assertIn("{first} and {last} in one argument", format_problem({".py": command}),
                              "the argument that repeats per range carries both ends of it")


class TheCommandForAFile(unittest.TestCase):
    def test_the_extension_picks_the_command_as_written(self):
        self.assertEqual(command_for({".py": PY}, Path("C:/other/a.PY"), WINDOWS), tuple(PY),
                         "the extension matches without case, and the command comes back as the user wrote it")

    def test_a_project_root_wins_for_its_own_files(self):
        value = {".py": PY, "C:/Work/App": {".py": LINT}}
        inside, outside = Path("C:/work/app/src/a.py"), Path("C:/work/other/a.py")
        self.assertEqual((command_for(value, inside, WINDOWS)[0], command_for(value, outside, WINDOWS)[0]),
                         ("ruff", "python"), "a project's own command applies under its root only")

    def test_no_command_for_an_extension_nobody_named(self):
        self.assertIsNone(command_for({".py": PY}, Path("C:/work/a.cpp"), WINDOWS),
                          "no command, nothing runs")


class ACommandIsFilledIn(unittest.TestCase):
    def test_the_path_fills_file(self):
        path = Path("C:/other/a.py")
        self.assertEqual(filled(PY, path), ("python", "-m", "py_compile", str(path)), "{file} becomes the path")

    def test_the_range_argument_repeats_once_per_range(self):
        path = Path("C:/work/a.cpp")
        self.assertEqual(filled(CLANG_FORMAT, path, [(3, 5), (9, 9)]),
                         ("clang-format", "--style=file", "--fallback-style=none", f"--assume-filename={path}",
                          "--lines=3:5", "--lines=9:9"),
                         "each range gets its own --lines, in the order given")


if __name__ == "__main__":
    unittest.main()
