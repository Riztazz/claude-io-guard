"""lib.logcap copies a background run's output into its log up to a cap, and the run goes on past it."""
import io
import sys
import tempfile
import unittest
from pathlib import Path

from ioguard.lib import logcap, proc


class TheLogStopsAtItsCap(unittest.TestCase):
    def test_output_past_the_cap_is_dropped_after_one_line_that_says_so(self):
        target = io.BytesIO()
        cut = logcap.copy(io.BytesIO(b"x" * 100), target, 40)
        self.assertEqual((cut, target.getvalue()), (True, b"x" * 40 + logcap.CUT),
                         "the log keeps its first 40 bytes and says where it stopped")

    def test_output_under_the_cap_is_copied_whole(self):
        target = io.BytesIO()
        cut = logcap.copy(io.BytesIO(b"one\ntwo\n"), target, 40)
        self.assertEqual((cut, target.getvalue()), (False, b"one\ntwo\n"), "nothing is cut under the cap")

    def test_a_background_run_past_the_cap_ends_on_its_own_with_the_log_capped(self):
        with tempfile.TemporaryDirectory(prefix="ioguard-logcap-") as folder:
            log = Path(folder) / "output.log"
            program = "import sys\nfor n in range(500): sys.stdout.write('line %04d\\n' % n)\nprint('END')\n"
            pump = proc.background([sys.executable, "-c", program], Path(folder), {"PATH": ""}, log, cap=1000)
            self.assertTrue(pump.wait(30), "the run ends on its own, never blocked by the cap")
            data = log.read_bytes()
        self.assertEqual((pump.exit_code, data[:9], data[1000:]), (0, b"line 0000", logcap.CUT),
                         "the log holds the first 1,000 bytes and the line that says it was cut")


if __name__ == "__main__":
    unittest.main()
