"""lib.locks names the processes that hold a file open: lsof's output parsed, and a live holder found on the
host's own platform. Its file_lock lets one io-guard process at a time hold a path."""
import subprocess
import sys
import time
import unittest

from ioguard.lib.context import first_in_file
from ioguard.lib.locks import Process, file_lock, holders, parse_lsof
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


class OneHolderOfAFileLockAtATime(unittest.TestCase):
    def test_a_second_holder_waits_and_then_times_out(self):
        with TemporaryProject() as data:
            with file_lock(data / "a.cpp", data):
                started = time.monotonic()
                with self.assertRaises(TimeoutError, msg="another holder times out, never waiting forever"), \
                        file_lock(data / "a.cpp", data, wait_s=0.2):
                    pass
                waited = time.monotonic() - started
            with file_lock(data / "a.cpp", data, wait_s=0.2):
                released = True
        self.assertGreaterEqual(waited, 0.2, "it waits the time it was given first")
        self.assertTrue(released, "once the first holder lets go, the next one gets the lock")

    def test_another_path_has_its_own_lock(self):
        with TemporaryProject() as data:
            with file_lock(data / "a.cpp", data), file_lock(data / "b.cpp", data, wait_s=0.2):
                both = True
        self.assertTrue(both, "two files lock apart")


class ASessionsProcessesShareTheirWarnings(unittest.TestCase):
    def test_a_key_is_new_once_in_the_file(self):
        with TemporaryProject() as data:
            path = data / "sessions" / "s1.warned"
            said = [first_in_file(path, data, key) for key in ("broken:a", "broken:a", 'quote"d')]
        self.assertEqual(said, [True, False, True], "the second process finds the key the first one wrote")


if __name__ == "__main__":
    unittest.main()
