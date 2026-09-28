"""io.run's call reads the same in the hook and in the tool: the argv it runs and the key the hook records."""
import unittest

from ioguard.lib import runs
from ioguard.lib.context import Probe, ToolVersion
from ioguard.lib.platform import Platform

WINDOWS = Platform("win32", True)
PROBE = Probe.unprobed(WINDOWS)


class ACallNamesOneCommand(unittest.TestCase):
    def test_argv_runs_as_given_and_a_body_runs_through_its_interpreter(self):
        python = ToolVersion("C:/Python314/python.exe", "3.14")
        probe = PROBE.__class__(**{**PROBE.__dict__, "python": python})
        self.assertEqual(runs.argv_of({"argv": ["git", "status"]}, probe, WINDOWS), ("git", "status"),
                         "an argv runs as the call gives it")
        self.assertEqual(runs.argv_of({"lang": "python", "code": "1"}, probe, WINDOWS, "C:/r/body.py"),
                         ("C:/Python314/python.exe", "C:/r/body.py"),
                         "a body runs through the probe's Python")
        self.assertIsNone(runs.argv_of({"lang": "cobol", "code": "1"}, probe, WINDOWS),
                          "a language with no interpreter runs nothing")

    def test_the_key_tells_calls_apart_by_what_they_run(self):
        keys = {runs.key({"argv": ["git", "fetch"]}), runs.key({"argv": ["git", "fetch", "-v"]}),
                runs.key({"lang": "python", "code": "a"}), runs.key({"lang": "python", "code": "b"})}
        self.assertEqual(len(keys), 4, "each command, and each body, has its own key")


if __name__ == "__main__":
    unittest.main()
