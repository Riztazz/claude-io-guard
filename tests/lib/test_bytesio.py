"""write_atomic lands exact bytes through a rename, retries a held file, and leaves no temporary behind."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ioguard.lib import bytesio


class AtomicWrites(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="ioguard-bytes-"))
        self.target = self.folder / "a.txt"

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_the_bytes_on_disk_are_the_bytes_given(self):
        data = b"\xef\xbb\xbfone\r\ntwo\rthree\n\x00"
        report = bytesio.write_atomic(self.target, data)
        self.assertEqual((self.target.read_bytes(), report.bytes_written, report.attempts),
                         (data, len(data), 1), "write_atomic lands every byte, BOM, CR and NUL included")

    def test_an_existing_file_is_replaced_whole(self):
        self.target.write_bytes(b"old content that is longer")
        bytesio.write_atomic(self.target, b"new")
        self.assertEqual(self.target.read_bytes(), b"new", "the new bytes replace the old file whole")

    def test_no_temporary_file_is_left_behind(self):
        bytesio.write_atomic(self.target, b"x")
        self.assertEqual([path.name for path in self.folder.iterdir()], ["a.txt"],
                         "the temporary file is renamed away, and nothing else stays")

    def test_a_held_file_is_retried_until_it_frees(self):
        real_replace = bytesio.os.replace
        calls = []

        def busy_twice(source, target):
            calls.append(target)
            if len(calls) < 3:
                raise PermissionError("held by another process")
            real_replace(source, target)

        with mock.patch.object(bytesio.os, "replace", side_effect=busy_twice), \
                mock.patch.object(bytesio.time, "sleep"):
            report = bytesio.write_atomic(self.target, b"x")
        self.assertEqual((report.attempts, self.target.read_bytes()), (3, b"x"),
                         "a rename refused twice succeeds on the third attempt")

    def test_a_file_held_past_the_retries_raises_and_cleans_up(self):
        with mock.patch.object(bytesio.os, "replace", side_effect=PermissionError("held")), \
                mock.patch.object(bytesio.time, "sleep"):
            with self.assertRaises(PermissionError, msg="the last refusal is raised, never swallowed"):
                bytesio.write_atomic(self.target, b"x", retries=2)
        self.assertEqual(list(self.folder.iterdir()), [], "the temporary file is removed after a failure")

    def test_a_read_can_stop_at_a_limit(self):
        self.target.write_bytes(b"0123456789")
        self.assertEqual(bytesio.read_bytes(self.target, 4), b"0123", "read_bytes honours its limit")

    def test_a_tail_holds_whole_lines_only(self):
        self.target.write_bytes(b"first line\nsecond\nthird\n")
        self.assertEqual((bytesio.read_tail(self.target, 12), bytesio.read_tail(self.target, 100)),
                         (b"third\n", b"first line\nsecond\nthird\n"),
                         "a tail starts after the line the limit cut, and a short file comes back whole")


if __name__ == "__main__":
    unittest.main()
