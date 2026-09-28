"""normalise turns a path as the agent wrote it into one absolute form on each platform."""
import os
import sys
import unittest
from pathlib import Path

from ioguard.lib.paths import LockTable, inside, link_target, msys_prefix, normalise, reserved, resolved
from ioguard.lib.platform import Platform, detect
from tests.support.project import TemporaryProject

if sys.platform == "win32":
    import _winapi

WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)


class PathsNormalise(unittest.TestCase):
    def test_a_windows_relative_path_joins_cwd_with_dots_folded(self):
        self.assertEqual(normalise("sub\\..\\a.txt", Path("C:\\work"), WINDOWS).as_posix(), "C:/work/a.txt",
                         "on Windows a relative path joins cwd and .. is folded")

    def test_a_windows_absolute_path_ignores_cwd(self):
        self.assertEqual(normalise("D:\\other\\a.txt", Path("C:\\work"), WINDOWS).as_posix(),
                         "D:/other/a.txt", "an absolute Windows path stands on its own")

    def test_a_windows_path_keeps_its_parts_on_any_host(self):
        self.assertEqual(normalise("src\\a.py", Path("C:/project"), WINDOWS).parts[-2:], ("src", "a.py"),
                         "a test that reads an event as Windows on macOS still gets separate parts")

    def test_a_macos_name_comes_back_as_nfc(self):
        decomposed = "cafe" + chr(0x301) + ".txt"
        self.assertEqual(normalise(decomposed, Path("/w"), MACOS).name, "caf" + chr(0xE9) + ".txt",
                         "on macOS a decomposed name is normalised to NFC, the form a user types")

    def test_reserved_reads_the_name_before_the_first_dot(self):
        names = ["nul", "NUL.txt", "con .log", "com1.tar.gz", "console.txt", "com10", "lpt0", "a.nul"]
        self.assertEqual([reserved(Path("C:/w") / name) for name in names],
                         ["nul", "nul", "con", "com1", None, None, None, None],
                         "Windows reads a device name before the first dot, spaces dropped, without case")

    def test_link_target_follows_a_linked_folder_and_leaves_a_plain_path(self):
        with TemporaryProject({"real/a.txt": b"x", "plain/b.txt": b"y"}) as root:
            link = root / "linked"
            if sys.platform == "win32":
                _winapi.CreateJunction(str(root / "real"), str(link))
            else:
                os.symlink(root / "real", link)
            found = (link_target(link / "a.txt"), link_target(link / "new.txt"),
                     link_target(root / "plain" / "b.txt"))
        self.assertEqual(found, (root / "real" / "a.txt", root / "real" / "new.txt", None),
                         "a file through a linked folder is where the link points, even one not written yet")

    def test_inside_finds_the_deepest_root_that_holds_a_path(self):
        roots = [Path("C:/Work"), Path("C:/work/app"), Path("C:/other")]
        found = [inside(Path(path), roots, WINDOWS) for path in ("C:/work/app/a.py", "C:/work/b.py", "D:/x")]
        self.assertEqual(found, [Path("C:/work/app"), Path("C:/Work"), None],
                         "the deepest root wins, names match without case on Windows, and none holds D:/x")

    def test_inside_keeps_case_where_the_file_system_does(self):
        self.assertIsNone(inside(Path("/Work/a"), [Path("/work")], Platform("linux", False)),
                          "a case-sensitive file system keeps Work and work apart")

    def test_git_bash_keeps_a_name_and_converts_a_path(self):
        cases = {"/Game/X/Y": "/Game/", "/PID": "/PID", "/p:Config=Debug": "/p:Config=Debug",
                 "--map=/Game/L": "--map=/Game/", "/c/Users/x": None, "/F": "/F", "/tmp/a": None, "//c": None,
                 "-I/usr/x": None, "relative/x": None, "/": None}
        for word, prefix in cases.items():
            with self.subTest(word=word):
                self.assertEqual(msys_prefix(word, ("tmp", "usr")), prefix,
                                 "a name keeps its slash, and a drive or POSIX root is converted as meant")

    def test_detect_names_this_platform(self):
        import sys
        self.assertEqual(detect().os, sys.platform, "detect reports the platform the tests run on")


class OneLockPerFile(unittest.TestCase):
    def test_two_names_for_one_file_share_its_lock(self):
        with TemporaryProject({"real/a.txt": b"x", "real/b.txt": b"y"}) as root:
            link = root / "linked"
            if sys.platform == "win32":
                _winapi.CreateJunction(str(root / "real"), str(link))
            else:
                os.symlink(root / "real", link)
            table = LockTable()
            same = (table.lock(root / "real" / "a.txt"), table.lock(link / "a.txt"),
                    table.lock(root / "real" / "sub" / ".." / "a.txt"))
            other = table.lock(root / "real" / "b.txt")
            self.assertEqual((resolved(link / "a.txt"), len({id(lock) for lock in same}), other in same),
                             (resolved(root / "real" / "a.txt"), 1, False),
                             "a path through a link and a path with .. name one file, which has one lock")

    def test_on_a_mac_a_decomposed_name_and_another_case_name_the_same_file(self):
        composed, decomposed = "caf" + chr(0xE9), "cafe" + chr(0x301)
        mac, linux = Platform("darwin", True), Platform("linux", False)
        self.assertEqual(resolved(Path(f"/w/{decomposed}.txt"), mac),
                         resolved(Path(f"/W/{composed}.TXT"), mac),
                         "task 36: APFS hands back NFD and ignores case, so both spellings share a lock")
        self.assertNotEqual(resolved(Path("/w/A.txt"), linux), resolved(Path("/w/a.txt"), linux),
                            "a file system that keeps case keeps two files")


if __name__ == "__main__":
    unittest.main()
