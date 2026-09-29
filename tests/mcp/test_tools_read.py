"""io.read returns a file's lines exactly as the file holds them, after its profile, a part at a time."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.fakes import FakeFs
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_read import SPECS, ReadInput, read
from ioguard.mcp.toolspec import ToolCall, ToolFailure, ToolRegistry

CWD = Path("C:/project")
WINDOWS = Platform("win32", True)


def reading(files: dict, path: str = "a.txt", **options) -> object:
    values = {**defaults().values, **{f"io.read.{name}": value for name, value in options.items()}}
    ctx = Context.fake(config=Config(MappingProxyType(values)), platform=WINDOWS, fs=FakeFs(files))
    given = ReadInput(path, **{key: value for key, value in options.items() if key in ("offset", "limit")})
    return read(given, ToolCall(lambda: ctx, CancelToken(), CWD, None))


class TheBytesComeBackAsTheyAre(unittest.TestCase):
    def test_a_crlf_file_with_a_bom_keeps_both_and_names_them(self):
        found = reading({CWD / "a.txt": b"\xef\xbb\xbfone\r\n\ttwo\r\n"})
        self.assertEqual((found.profile, found.text), ("CRLF, BOM, UTF-8, tabs, 2 lines",
                                                       chr(0xFEFF) + "one\r\n\ttwo\r\n"),
                         "the profile names what the built-in Read hides, and the text keeps it")
        self.assertEqual(found.sha256, hashlib.sha256(b"\xef\xbb\xbfone\r\n\ttwo\r\n").hexdigest(),
                         "the hash of the bytes read is the expect_hash an io tool checks")
        self.assertIn("     1| [BOM]one[CR]", found.render(), "the text copy marks the BOM and each CR")

    def test_a_binary_file_gives_its_first_bytes(self):
        found = reading({CWD / "a.bin": b"\x00\x01\x02" * 40}, "a.bin")
        self.assertEqual((found.binary, found.text, found.head_hex[:8]), (True, "", "00 01 02"),
                         "a NUL marks the bytes as binary, decided from the bytes rather than the name")

    def test_a_part_names_the_call_for_the_rest(self):
        data = b"".join(b"line %d\n" % number for number in range(1, 11))
        found = reading({CWD / "a.txt": data}, offset=3, limit=2)
        self.assertEqual((found.first_line, found.last_line, found.total_lines, found.text),
                         (3, 4, 10, "line 3\nline 4\n"), "offset and limit count lines from 1")
        self.assertEqual(found.next, "Call mcp__plugin_io-guard_io__io_read with offset 5 for the rest.",
                         "the next call is named, with the tool's callable name")
        self.assertIn("     3| line 3", found.render(), "the copy numbers lines as the file does")

    def test_max_chars_stops_a_part_early(self):
        found = reading({CWD / "a.txt": b"aaaa\nbbbb\ncccc\n"}, max_chars=11)
        self.assertEqual((found.last_line, found.next.endswith("with offset 3 for the rest.")), (2, True),
                         "a part stops before the line that would pass max_chars")


class ALongFileComesBackUpToItsOwnLimit(unittest.TestCase):
    """io.read through the registry, as the server answers it, with a folder for a result that spills."""

    def answer(self, lines: int, **config) -> dict:
        folder = Path(tempfile.mkdtemp(prefix="ioguard-read-"))
        self.addCleanup(shutil.rmtree, folder, True)
        data = b"".join(b"line %05d of a file read whole\n" % number for number in range(1, lines + 1))
        values = {**defaults().values, **config}
        ctx = Context.fake(config=Config(MappingProxyType(values)), platform=WINDOWS,
                           fs=FakeFs({CWD / "a.txt": data}))
        tools = ToolRegistry()
        for each in SPECS:
            tools.register(each)
        return tools.call("io.read", {"path": "a.txt"}, ToolCall(lambda: ctx, CancelToken(), CWD, folder))

    def test_a_50_kb_file_reads_whole(self):
        found = self.answer(1600)["structuredContent"]
        self.assertEqual((found.get("saved"), found.get("last_line"), found.get("next")), (None, 1600, ""),
                         "51,200 bytes are under io.read.max_chars, so the whole file comes back")

    def test_a_300_kb_file_pages_with_next(self):
        found = self.answer(9600)["structuredContent"]
        self.assertEqual((found.get("saved"), found.get("first_line")), (None, 1),
                         "the first part comes back in the answer, not in a file")
        self.assertTrue(found.get("next", "").endswith("for the rest."), "and it names the call for the rest")

    def test_a_result_that_spills_keeps_its_paging_fields(self):
        found = self.answer(9600, **{"io.read.max_chars": 500_000})["structuredContent"]
        self.assertTrue(found.get("saved"), "past the answer's own limit the text goes to a file")
        self.assertEqual((found.get("first_line"), found.get("total_lines")), (1, 9600),
                         "the fields that are not the long text stay in the answer")
        self.assertIn("next", found, "including the call for the rest")


class WhatCannotBeReadIsNamed(unittest.TestCase):
    def test_a_missing_file_and_a_file_past_max_bytes_fail_with_their_codes(self):
        for files, options, code in (({}, {}, Code.PATH_NOT_FOUND),
                                     ({CWD / "a.txt": b"x" * 20}, {"max_bytes": 10}, Code.READ_TOO_LARGE)):
            with self.subTest(code=code):
                with self.assertRaises(ToolFailure) as failure:
                    reading(files, **options)
                self.assertEqual(failure.exception.result.code, code, "the model reads the code and the fix")


if __name__ == "__main__":
    unittest.main()
