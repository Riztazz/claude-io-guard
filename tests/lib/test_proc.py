"""proc.run starts a program from a list, and a timeout or a missing program is a result, not a raise."""
import sys
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

    def test_a_timeout_is_a_result(self):
        result = proc.run([sys.executable, "-c", "import time; time.sleep(5)"], HERE, timeout_s=0.3)
        self.assertEqual((result.timed_out, result.exit_code), (True, None), "a timeout ends the wait")

    def test_a_missing_program_is_a_result(self):
        result = proc.run(["io-guard-no-such-program"], HERE)
        self.assertEqual((result.exit_code, result.ok), (None, False), "a missing program is not ok")
        self.assertTrue(result.start_error, "the result says why the program did not start")


if __name__ == "__main__":
    unittest.main()
