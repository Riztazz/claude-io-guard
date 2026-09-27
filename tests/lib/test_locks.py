"""lib.locks names the processes that hold a file open: lsof's output parsed, and a live holder found on the
host's own platform."""
import subprocess
import sys
import unittest

from ioguard.lib.locks import Process, holders, parse_lsof
from ioguard.lib.platform import detect
from tests.support.project import TemporaryProject

HOLD = "import sys; handle = open(sys.argv[1], 'rb'); print('open', flush=True); sys.stdin.read()"


class LsofOutputParses(unittest.TestCase):
    def test_each_process_is_its_id_and_command(self):
        raw = b"p812\ncpython3.14\np95\ncclang-format\n"
        self.assertEqual(parse_lsof(raw), (Process(812, "python3.14"), Process(95, "clang-format")),
                         "lsof -F pc gives a p line and a c line per process")

    def test_no_holder_is_no_process(self):
        self.assertEqual(parse_lsof(b""), (), "a file nobody holds has no holder")


@unittest.skipUnless(sys.platform in ("win32", "darwin"), "the Restart Manager and lsof answer there only")
class ALiveHolderIsNamed(unittest.TestCase):
    def test_a_child_that_holds_the_file_is_named(self):
        with TemporaryProject({"held.txt": b"x"}) as root:
            path = root / "held.txt"
            child = subprocess.Popen([sys.executable, "-c", HOLD, str(path)], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE)
            try:
                child.stdout.readline()
                found = holders(path, detect())
            finally:
                child.communicate(b"", timeout=30)
        self.assertIn(child.pid, [process.pid for process in found],
                      "the process holding the file open is named, by the platform's own API")


if __name__ == "__main__":
    unittest.main()
