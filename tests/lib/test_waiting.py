"""A project's commands that run a file from inside the project are named, through the file system port."""
import unittest
from pathlib import Path

from ioguard.lib import waiting
from ioguard.lib.fakes import FakeFs
from ioguard.lib.platform import Platform

WINDOWS = Platform("win32", True)
PROJECT = Path("C:/project")


class ACommandThatRunsAProjectFileIsNamed(unittest.TestCase):
    def test_a_file_inside_the_project_is_named_and_one_outside_is_not(self):
        outside = Path("C:/elsewhere/lint.py")
        fs = FakeFs({PROJECT / "tools" / "check.py": b"", outside: b"", PROJECT / "linked" / "lint.py": b""},
                    links={PROJECT / "linked": outside.parent})
        held = {"verify": {".py": ["python", "tools/check.py", "../elsewhere/lint.py", "linked/lint.py",
                                   "tools/missing.py", "tools"]}}
        self.assertEqual(waiting.inside(held, PROJECT, fs, WINDOWS), ["tools/check.py"],
                         "only a file that is inside the project, by its real path, is one a pull can change")


if __name__ == "__main__":
    unittest.main()
