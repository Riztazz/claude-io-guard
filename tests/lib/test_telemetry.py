"""Telemetry writes one line per event into its session's monthly file, and never file content."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ioguard import TELEMETRY_SCHEMA
from ioguard.lib.telemetry import (Telemetry, TelemetryEvent, erase, expire, program_of, session_files,
                                   shrink_heads, trace_from)

WHEN = datetime(2026, 9, 27, 14, 3, 11, 412000, tzinfo=timezone.utc)
NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


def event(**fields) -> TelemetryEvent:
    return TelemetryEvent(**{"ts": WHEN, "session": "s1", "event": "PreToolUse", "surface": "mcp_hook",
                             "platform": "win32", **fields})


class TelemetryLines(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-telemetry-"))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def test_an_event_lands_in_its_sessions_monthly_file(self):
        Telemetry(self.data).record(event(code="GUARD_ERROR"))
        lines = (self.data / "events" / "2026-09" / "s1.jsonl").read_bytes().splitlines()
        line = json.loads(lines[0])
        self.assertEqual((len(lines), line["schema"], line["code"], line["ts"]),
                         (1, TELEMETRY_SCHEMA, "GUARD_ERROR", "2026-09-27T14:03:11.412Z"),
                         "one line, with the schema number and a millisecond UTC timestamp")

    def test_a_command_is_cut_to_200_characters(self):
        Telemetry(self.data).record(event(cmd_head="x" * 500))
        line = json.loads((self.data / "events" / "2026-09" / "s1.jsonl").read_bytes())
        self.assertEqual(len(line["cmd_head"]), 200, "telemetry keeps at most 200 characters of a command")

    def test_disabled_telemetry_writes_nothing(self):
        Telemetry(self.data, enabled=False).record(event())
        self.assertFalse((self.data / "events").exists(), "with telemetry off, no file is created")

    def test_memory_telemetry_keeps_events_in_a_list(self):
        sink = Telemetry.memory()
        sink.record(event(check="demo"))
        self.assertEqual([item.check for item in sink.events], ["demo"], "a memory sink keeps each event")


class OldTelemetryIsDeleted(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-retention-"))
        self.addCleanup(shutil.rmtree, self.data, True)

    def written(self, name: str, days_ago: float) -> Path:
        """A session file whose last line is days_ago days before NOW."""
        path = self.data / "events" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}\n")
        stamp = (NOW - timedelta(days=days_ago)).timestamp()
        os.utime(path, (stamp, stamp))
        return path

    def left(self) -> list[str]:
        return [path.relative_to(self.data / "events").as_posix() for path in session_files(self.data)]

    def test_a_file_past_the_retention_goes_and_one_inside_it_stays(self):
        self.written("2026-06/old.jsonl", 91)
        self.written("2026-07/edge.jsonl", 89)
        self.written("2026-10/new.jsonl", 1)
        gone = expire(self.data, 90, NOW)
        month = (self.data / "events" / "2026-06").exists()
        self.assertEqual(([path.name for path in gone], self.left(), month),
                         (["old.jsonl"], ["2026-07/edge.jsonl", "2026-10/new.jsonl"], False),
                         "91 days goes with its emptied month, and 89 stays")

    def test_zero_days_keeps_every_file(self):
        self.written("2026-01/ancient.jsonl", 400)
        self.assertEqual((expire(self.data, 0, NOW), self.left()), ([], ["2026-01/ancient.jsonl"]),
                         "a retention of 0 deletes nothing")

    def test_erase_deletes_every_file_and_keeps_this_months_folder(self):
        self.written("2026-09/a.jsonl", 20)
        self.written("2026-10/b.jsonl", 0)
        gone = erase(self.data, NOW)
        folders = sorted(path.name for path in (self.data / "events").iterdir())
        self.assertEqual((len(gone), self.left(), folders), (2, [], ["2026-10"]),
                         "every file goes, and a session writing this month still has its folder")


class OldCommandHeadsShrink(unittest.TestCase):
    LINES = [{"ts": "2026-09-01T00:00:00+00:00", "cmd_head": "git commit -m 'token=abc123'", "code": "X"},
             {"ts": "2026-09-01T00:00:01+00:00", "cmd_head": "\"C:/Git/cmd/git.exe\" push", "code": None},
             {"ts": "2026-09-01T00:00:02+00:00", "cmd_head": None}]

    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-heads-"))
        self.addCleanup(shutil.rmtree, self.data, True)

    def written(self, name: str, days_ago: float) -> Path:
        path = self.data / "events" / "2026-09" / f"{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"".join(json.dumps(line).encode("ascii") + b"\n" for line in self.LINES))
        stamp = (NOW - timedelta(days=days_ago)).timestamp()
        os.utime(path, (stamp, stamp))
        return path

    @staticmethod
    def heads(path: Path) -> list:
        return [json.loads(line).get("cmd_head") for line in path.read_bytes().splitlines()]

    def test_a_file_past_the_days_keeps_only_each_program_and_its_time(self):
        old, new = self.written("old", 8), self.written("new", 6)
        before = old.stat().st_mtime
        self.assertEqual(shrink_heads(self.data, 7, NOW), [old], "only the file past 7 days is rewritten")
        self.assertEqual((self.heads(old), self.heads(new)[0], old.stat().st_mtime),
                         (["git", "git.exe", None], "git commit -m 'token=abc123'", before),
                         "the old heads keep their program, the new file keeps its words, and the old file "
                         "keeps the time expire reads")
        self.assertEqual(json.loads(old.read_bytes().splitlines()[0])["code"], "X", "every other field stays")
        self.assertEqual(shrink_heads(self.data, 7, NOW), [], "a file already cut is not written again")

    def test_zero_keeps_every_head(self):
        old = self.written("old", 80)
        self.assertEqual((shrink_heads(self.data, 0, NOW), self.heads(old)[0]),
                         ([], "git commit -m 'token=abc123'"), "0 keeps the heads whole")

    def test_the_program_is_the_first_word_without_quotes_or_folder(self):
        cases = {"git push": "git", "'C:\\Program Files\\x.exe' -v": "x.exe", "   ": "",
                 "/usr/bin/python3 -c 1": "python3", "\"C:/Git/cmd/git.exe\" push": "git.exe"}
        for command, program in cases.items():
            with self.subTest(command=command):
                self.assertEqual(program_of(command), program, "the bare first word")


class TraceContexts(unittest.TestCase):
    def test_one_tool_use_always_gives_the_same_trace_id(self):
        self.assertEqual(trace_from("toolu_01ABC", None).trace_id, trace_from("toolu_01ABC", None).trace_id,
                         "every record about one tool use shares a trace id")

    def test_a_traceparent_supplies_the_trace_and_the_parent_span(self):
        trace = trace_from("toolu_01ABC", "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        self.assertEqual((trace.trace_id, trace.parent_span_id),
                         ("4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7"),
                         "a W3C traceparent sets the trace id and the parent span")

    def test_a_malformed_traceparent_falls_back_to_the_tool_use(self):
        self.assertEqual(trace_from("toolu_01ABC", "garbage").trace_id,
                         trace_from("toolu_01ABC", None).trace_id,
                         "a traceparent that is not W3C form is ignored")


if __name__ == "__main__":
    unittest.main()
