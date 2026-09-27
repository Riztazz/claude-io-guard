"""The pre-commit check compares each staged file with its last commit, and the shipped script stops a commit
that carries byte damage."""
import subprocess
import sys
import unittest
from pathlib import Path

from ioguard.cli.precommit import staged_results
from ioguard.lib.fakes import FakeGit
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code
from tests import REPO
from tests.support.project import TemporaryProject

ROOT = Path("C:/work")
WINDOWS = Platform("win32", True)
SCRIPT = REPO / "plugins" / "io-guard" / "scripts" / "precommit.py"
BOM = b"\xef\xbb\xbf"


def found(changes: dict[str, tuple[bytes | None, bytes]], ascii_only: list[str] = ()) -> list[Code]:
    """The codes for staged files given as {name: (bytes at HEAD or None, staged bytes)}."""
    blobs = {}
    for name, (before, after) in changes.items():
        blobs[f":{name}"] = after
        if before is not None:
            blobs[f"HEAD:{name}"] = before
    git = FakeGit(root=ROOT, staged_paths=tuple(changes), blobs=blobs)
    return [result.code for result in staged_results(ROOT, git, list(ascii_only), WINDOWS)]


class TheStagedBytesAreCompared(unittest.TestCase):
    def test_each_kind_of_damage_is_named(self):
        cases = {"endings": ({"a.txt": (b"one\r\ntwo\r\n", b"one\ntwo\n")}, [Code.EOL_MISMATCH]),
                 "bom": ({"a.txt": (BOM + b"one\n", b"one\n")}, [Code.BOM_CHANGED]),
                 "control": ({"a.txt": (b"one\n", b"one\x07\n")}, [Code.CONTROL_BYTES_ADDED]),
                 "new file": ({"n.txt": (None, b"x" + chr(0xFFFD).encode("utf-8"))}, [Code.ENCODING_INVALID]),
                 "clean": ({"a.txt": (b"one\n", b"one\ntwo\n")}, [])}
        for name, (changes, codes) in cases.items():
            with self.subTest(name):
                self.assertEqual(found(changes), codes, f"the staged change is judged by its bytes: {name}")

    def test_ascii_only_names_its_extensions(self):
        change = {"a.py": (b"x = 1\n", "x = '".encode() + chr(0x2192).encode("utf-8") + b"'\n")}
        self.assertEqual((found(change), found(change, [".PY"])), ([], [Code.NON_ASCII_ADDED]),
                         "non-ASCII is a finding only where the project keeps ASCII")

    def test_a_binary_file_is_skipped(self):
        self.assertEqual(found({"a.bin": (b"\x00\x01", b"\x00\x02")}), [],
                         "a binary file has no text to judge")


class TheScriptGuardsARealCommit(unittest.TestCase):
    def commit(self, root: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-c", "user.name=io-guard test", "-c", "user.email=test@localhost",
                               "commit", "-q", "-m", "change"], cwd=root, capture_output=True, timeout=60)

    def test_a_commit_that_drops_crlf_stops_and_a_clean_one_goes_through(self):
        with TemporaryProject({"a.txt": b"one\r\ntwo\r\n"}, git=True) as root:
            hook = root / ".git" / "hooks" / "pre-commit"
            python = Path(sys.executable).as_posix()
            hook.write_bytes(f'#!/bin/sh\nexec "{python}" "{SCRIPT.as_posix()}"\n'.encode())
            hook.chmod(0o755)
            (root / "a.txt").write_bytes(b"one\ntwo\n")
            subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, timeout=60)
            stopped = self.commit(root)
            (root / "a.txt").write_bytes(b"one\r\ntwo\r\nthree\r\n")
            subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, timeout=60)
            passed = self.commit(root)
        output = (stopped.stdout + stopped.stderr).decode("utf-8", "replace")
        self.assertEqual((stopped.returncode != 0, passed.returncode), (True, 0),
                         f"the hook stops the damaged commit and lets the clean one through: {output!r}")
        self.assertIn("a.txt: EOL_MISMATCH: The staged change changed a.txt from CRLF to LF line endings.",
                      output, "the hook names the file, the code and what changed")


if __name__ == "__main__":
    unittest.main()
