"""A progress reporter sends notifications/progress under its call's token, at most twice a second, and
sends nothing for a call whose request carried no token."""
import unittest

from ioguard.mcp.progress import ProgressReporter


class ProgressIsThrottled(unittest.TestCase):
    def test_reports_closer_than_half_a_second_are_dropped(self):
        now, sent = [0.0], []
        reporter = ProgressReporter(sent.append, "t", lambda: now[0])
        for moment in (0.0, 0.2, 0.49, 0.5, 0.9, 1.1):
            now[0] = moment
            reporter.report(moment, "working")
        self.assertEqual([message["params"]["progress"] for message in sent], [0.0, 0.5, 1.1],
                         "one report per half second, each under the token")

    def test_a_call_without_a_token_reports_nothing(self):
        sent = []
        self.assertFalse(ProgressReporter(sent.append, None).report(1.0) or sent,
                         "no progressToken, no notification")


if __name__ == "__main__":
    unittest.main()
