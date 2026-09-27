"""normalise turns a path as the agent wrote it into one absolute form on each platform."""
import unittest
from pathlib import Path

from ioguard.lib.paths import normalise
from ioguard.lib.platform import Platform, detect

WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)


class PathsNormalise(unittest.TestCase):
    def test_a_windows_relative_path_joins_cwd_with_dots_folded(self):
        self.assertEqual(str(normalise("sub\\..\\a.txt", Path("C:\\work"), WINDOWS)), "C:\\work\\a.txt",
                         "on Windows a relative path joins cwd and .. is folded")

    def test_a_windows_absolute_path_ignores_cwd(self):
        self.assertEqual(str(normalise("D:/other/a.txt", Path("C:\\work"), WINDOWS)), "D:\\other\\a.txt",
                         "an absolute Windows path stands on its own, with backslashes")

    def test_a_macos_name_comes_back_as_nfc(self):
        decomposed = "cafe" + chr(0x301) + ".txt"
        self.assertEqual(normalise(decomposed, Path("/w"), MACOS).name, "caf" + chr(0xE9) + ".txt",
                         "on macOS a decomposed name is normalised to NFC, the form a user types")

    def test_detect_names_this_platform(self):
        import sys
        self.assertEqual(detect().os, sys.platform, "detect reports the platform the tests run on")


if __name__ == "__main__":
    unittest.main()
