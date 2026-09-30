"""A heartbeat survives its trip through the file, and bytes that are not one read as nothing."""
import unittest
from datetime import datetime, timedelta, timezone

from ioguard.lib.heartbeat import Era, Heartbeat, parse

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


if __name__ == "__main__":
    unittest.main()
