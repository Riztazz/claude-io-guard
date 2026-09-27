"""lib.editorconfig gives the properties that apply to a file, from the .editorconfig files above it."""
import unittest
from pathlib import Path

from ioguard.lib import editorconfig


def read_from(files: dict[str, str]):
    return lambda path: files.get(path.as_posix())


class GlobsMatchAsTheFormatSays(unittest.TestCase):
    def test_globs(self):
        cases = {("*.py", "src/a.py"): True, ("*.py", "a.pyc"): False, ("*.{h,cpp}", "x/y.cpp"): True,
                 ("src/*.md", "src/a.md"): True, ("src/*.md", "src/x/a.md"): False,
                 ("src/**.md", "src/x/a.md"): True, ("**/*.md", "a.md"): True,
                 ("[Mm]akefile", "Makefile"): True, ("a?.txt", "ab.txt"): True,
                 ("[!a]*.txt", "a1.txt"): False}
        for (glob, relative), expected in cases.items():
            with self.subTest(glob=glob, path=relative):
                self.assertEqual(editorconfig.matches(glob, relative), expected,
                                 "the glob covers what it names")


class PropertiesMerge(unittest.TestCase):
    def test_nearer_files_and_later_sections_win_and_root_stops_the_walk(self):
        files = {"C:/.editorconfig": "[*]\nend_of_line = cr\n",
                 "C:/p/.editorconfig": "root = true\n[*]\nend_of_line = lf\nindent_style = space\n"
                                       "[*.cpp]\nindent_style = tab\n",
                 "C:/p/src/.editorconfig": "[*.cpp]\nend_of_line = CRLF\n"}
        found = editorconfig.properties(Path("C:/p/src/a.cpp"), read_from(files))
        self.assertEqual((found["end_of_line"], found["indent_style"]), ("crlf", "tab"),
                         "the nearer file and the later section win, and nothing above root = true counts")


if __name__ == "__main__":
    unittest.main()
