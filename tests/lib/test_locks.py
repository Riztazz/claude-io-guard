"""lib.locks names the processes that hold a file open: lsof's output parsed, and a live holder found on the
host's own platform. Its file_lock lets one io-guard process at a time hold a path."""
import os
import re
import subprocess
import sys
import time
import unittest

from ioguard.lib.context import first_in_file
from ioguard.lib.locks import WANT_S, Process, file_lock, holders, parse_lsof, wanted_by_another
from ioguard.lib.platform import detect
from tests import PLUGIN_SCRIPTS
from tests.support.project import TemporaryProject

HOLD = "import sys; handle = open(sys.argv[1], 'rb'); print('open', flush=True); sys.stdin.read()"
TAKER = """
import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from ioguard.lib.locks import file_lock
data, key = Path(sys.argv[2]), sys.argv[3]
print("ready", flush=True)
sys.stdin.readline()
for _ in range(20):
    with file_lock(data / "a.txt", data):
        time.sleep(0.03)
        with open(data / "order.txt", "a") as out:
            out.write(key)
"""


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

    def test_two_processes_that_take_the_lock_in_a_loop_take_turns(self):
        with TemporaryProject() as data:
            pipes = {"stdin": subprocess.PIPE, "stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
            children = [subprocess.Popen([sys.executable, "-c", TAKER, str(PLUGIN_SCRIPTS), str(data), key],
                                         **pipes) for key in "AB"]
            for child in children:
                child.stdout.readline()
            for child in children:
                child.stdin.write(b"go\n")
                child.stdin.flush()
            errors = [child.communicate(timeout=120)[1] for child in children]
            order = (data / "order.txt").read_text(encoding="ascii")
        longest = max(len(run) for run in re.findall(r"A+|B+", order))
        self.assertEqual((sorted(order), errors), (sorted("A" * 20 + "B" * 20), [b"", b""]),
                         "both processes finish every turn")
        self.assertLessEqual(longest, 4, f"a waiter gets the lock between the other's turns: {order}")

    def test_a_fresh_mark_from_another_process_makes_way_and_an_old_or_own_one_does_not(self):
        with TemporaryProject() as data:
            want = data / "x.want"
            cases = {"another's fresh mark": (b"1", 0, True), "its own mark": (b"me", 0, False),
                     "an old mark": (b"1", WANT_S * 5, False)}
            for name, (owner, age, steps_aside) in cases.items():
                with self.subTest(name):
                    want.write_bytes(owner)
                    stamp = time.time() - age
                    os.utime(want, (stamp, stamp))
                    self.assertEqual(wanted_by_another(want, b"me"), steps_aside,
                                     "only another waiter still waiting gets the turn")
            want.unlink()
            self.assertFalse(wanted_by_another(want, b"me"), "no mark, no one to make way for")

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
