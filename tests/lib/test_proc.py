"""proc.run starts a program from a list, and a timeout or a missing program is a result, not a raise."""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ioguard.lib import proc

HERE = Path(__file__).parent


class ProgramsRun(unittest.TestCase):
    def test_a_program_gives_its_exit_code_and_output(self):
        result = proc.run([sys.executable, "-c", "import sys; sys.stdout.write('hi'); sys.exit(3)"], HERE)
        self.assertEqual((result.exit_code, result.stdout, result.ok), (3, b"hi", False),
                         "run returns the exit code and the raw output")

    def test_an_argument_with_quotes_and_spaces_arrives_whole(self):
        tricky = 'say "hi" and $HOME `x` C:\\temp\\new'
        result = proc.run([sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", tricky], HERE)
        self.assertEqual(result.stdout.decode("utf-8"), tricky, "no shell re-reads an argument")

    def test_stdin_carries_the_given_bytes_and_nothing_of_the_callers(self):
        echo = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
        given = proc.run(echo, HERE, stdin=b"a\r\nb\n")
        empty = proc.run(echo, HERE, timeout_s=5)
        self.assertEqual((given.stdout, empty.stdout, empty.timed_out), (b"a\r\nb\n", b"", False),
                         "a program reads the bytes it is given, and without any it reads an ended stdin, "
                         "never the io server's messages")

    def test_a_timeout_is_a_result(self):
        result = proc.run([sys.executable, "-c", "import time; time.sleep(5)"], HERE, timeout_s=0.3)
        self.assertEqual((result.timed_out, result.exit_code), (True, None), "a timeout ends the wait")

    def test_a_background_program_logs_its_output_and_tells_when_it_ends(self):
        log = Path(tempfile.mkdtemp(prefix="ioguard-proc-")) / "out" / "run.log"
        self.addCleanup(shutil.rmtree, log.parent.parent, True)
        ended = threading.Event()
        pump = proc.background([sys.executable, "-c", "import sys; print('out', flush=True); "
                                "print('err', file=sys.stderr); sys.exit(4)"], HERE, os.environ, log)
        pump.when_done(ended.set)
        self.assertTrue(pump.wait(30) and ended.wait(5), "the waiter thread sees the end and calls back")
        self.assertEqual((pump.exit_code, log.read_bytes().split()), (4, [b"out", b"err"]),
                         "stdout and stderr share one log, and the exit code is kept")
        called = []
        pump.when_done(lambda: called.append(True))
        self.assertEqual(called, [True], "a callback after the end runs at once")

    def test_stopping_a_background_program_ends_what_it_started(self):
        log = Path(tempfile.mkdtemp(prefix="ioguard-proc-")) / "run.log"
        self.addCleanup(shutil.rmtree, log.parent, True)
        child = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; " \
                "time.sleep(60)']); print('started', flush=True); time.sleep(60)"
        pump = proc.background([sys.executable, "-c", child], HERE, os.environ, log)
        started = time.monotonic()
        while b"started" not in log.read_bytes() and time.monotonic() - started < 30:
            pump.wait(0.05)
        pump.stop()
        self.assertTrue(pump.done.is_set(), "stop waits for the program to end")

    def test_a_missing_program_is_a_result(self):
        result = proc.run(["io-guard-no-such-program"], HERE)
        self.assertEqual((result.exit_code, result.ok), (None, False), "a missing program is not ok")
        self.assertTrue(result.start_error, "the result says why the program did not start")


if __name__ == "__main__":
    unittest.main()
