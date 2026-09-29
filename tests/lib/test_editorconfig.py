"""lib.editorconfig gives the properties that apply to a file, from the .editorconfig files above it."""
import time
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


    def test_a_glob_of_many_stars_takes_linear_time(self):
        started = time.perf_counter()
        found = editorconfig.matches("*a*a*a*a*a*a*a*b", "a" * 250)
        self.assertEqual((found, time.perf_counter() - started < 0.5), (False, True),
                         "a glob from a repository cannot stall the server on a long file name")

    def test_braces_nest_and_a_double_star_crosses_folders(self):
        cases = {("{src,lib}/**/*.{c,h}", "lib/x/y/z.h"): True, ("{src,lib}/**/*.{c,h}", "doc/z.h"): False,
                 ("**/*.md", "a/b/c.md"): True, ("a/**/b", "a/b"): True, ("*.{a,{b,c}}", "x.c"): True}
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
