"""lib.verify checks the shape of the user's verify commands and finds the one for a written file."""
import unittest
from pathlib import Path

from ioguard.lib.platform import Platform
from ioguard.lib.verify import command_for, shape_problem

WINDOWS = Platform("win32", True)
PY = ["python", "-m", "py_compile", "{file}"]
LINT = ["ruff", "check", "{file}"]
HERE = Path.cwd().anchor + "work/app"      # a project root that is absolute on the host running the test


class TheShapeIsChecked(unittest.TestCase):
    def test_good_values_pass(self):
        for value in ({}, {".py": PY}, {".py": PY, HERE: {".PY": LINT}}):
            with self.subTest(value=value):
                self.assertIsNone(shape_problem(value), "extensions and absolute project roots are the keys")

    def test_each_mistake_is_named(self):
        cases = {"no placeholder": ({".py": ["python", "-m", "py_compile"]}, "{file}"),
                 "one string": ({".py": "python -m py_compile {file}"}, "list of strings"),
                 "bad key": ({"py": PY}, "neither a file extension"),
                 "relative root": ({"work/app": {".py": PY}}, "absolute project folder"),
                 "project not an object": ({HERE: PY}, "object of extensions"),
                 "bad project command": ({HERE: {".py": []}}, "list of strings")}
        for name, (value, words) in cases.items():
            with self.subTest(name):
                self.assertIn(words, shape_problem(value), "the message says what to fix")


class TheCommandForAFile(unittest.TestCase):
    def test_the_extension_picks_the_command_and_the_path_fills_it(self):
        path = Path("C:/other/a.PY")
        self.assertEqual(command_for({".py": PY}, path, WINDOWS), ("python", "-m", "py_compile", str(path)),
                         "the extension matches without case, and {file} becomes the path")

    def test_a_project_root_wins_for_its_own_files(self):
        value = {".py": PY, "C:/Work/App": {".py": LINT}}
        inside, outside = Path("C:/work/app/src/a.py"), Path("C:/work/other/a.py")
        self.assertEqual((command_for(value, inside, WINDOWS)[0], command_for(value, outside, WINDOWS)[0]),
                         ("ruff", "python"), "a project's own command applies under its root only")

    def test_no_command_for_an_extension_nobody_named(self):
        self.assertIsNone(command_for({".py": PY}, Path("C:/work/a.cpp"), WINDOWS),
                          "no command, nothing runs")


if __name__ == "__main__":
    unittest.main()
