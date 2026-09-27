"""Telemetry writes one line per event into its session's monthly file, and never file content."""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ioguard import TELEMETRY_SCHEMA
from ioguard.lib.telemetry import Telemetry, TelemetryEvent, trace_from

WHEN = datetime(2026, 9, 27, 14, 3, 11, 412000, tzinfo=timezone.utc)


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
