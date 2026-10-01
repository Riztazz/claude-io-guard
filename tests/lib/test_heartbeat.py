"""A heartbeat survives its trip through the file, and bytes that are not one read as nothing."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ioguard.lib.heartbeat import Era, Heartbeat, parse, quiet

NOW = datetime(2026, 9, 28, 6, 0, tzinfo=timezone.utc)


class AHeartbeatRoundTrips(unittest.TestCase):
    def test_encode_then_parse_gives_the_same_heartbeat(self):
        beat = Heartbeat(4242, "s1", Era.LEGACY, NOW, NOW + timedelta(seconds=5))
        for kept in (beat, beat.again(NOW + timedelta(seconds=10), Era.MODERN)):
            with self.subTest(era=kept.era):
                self.assertEqual(parse(kept.encode()), kept, "the file holds each field and time zone")

    def test_bytes_that_are_not_a_heartbeat_read_as_none(self):
        for data in (b"", b"{", b'{"pid": 1}', b"\xff\xfe"):
            with self.subTest(data=data):
                self.assertIsNone(parse(data), "a torn or foreign file says nothing about the server")


class AHeartbeatLeavesNothingToSay(unittest.TestCase):
    def test_a_young_beat_or_a_clean_stop_is_quiet_and_an_old_beat_is_not(self):
        beat = Heartbeat(4242, "s1", Era.MODERN, NOW, NOW)
        cases = {("age 10 s, stale_s 30", 10, 30): True, ("age 31 s, stale_s 30", 31, 30): False,
                 ("age 10 s, stale_s 5", 10, 5): True, ("age 11 s, stale_s 5", 11, 5): False}
        for (name, age, stale), expected in cases.items():
            with self.subTest(name):
                self.assertEqual(quiet(beat.encode(), NOW + timedelta(seconds=age), stale), expected,
                                 "a stale_s under FRESH_S counts as FRESH_S, the hook's own fast answer")
        stopped = replace(beat, stopped=NOW).encode()
        self.assertTrue(quiet(stopped, NOW + timedelta(hours=1)), "a server that stopped cleanly did not die")
        self.assertTrue(quiet(b"{", NOW), "a torn file says nothing")


if __name__ == "__main__":
    unittest.main()
