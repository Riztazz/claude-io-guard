"""The report merges every session's telemetry file for the days asked, counts what io-guard fixed, warned
about and refused, times the calls, and fits one screen on a generated week."""
import json
import random
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ioguard.cli import report
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.fakes import FakeClock
from ioguard.lib.results import Code, Layer, Result
from ioguard.lib.telemetry import Telemetry, TelemetryEvent, TraceContext
from tests.checks.test_pipeline import bash_event, pipeline_of, rewriting, saying

NOW = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)     # a week that starts in September
TOOLS = ("Bash", "Edit", "Read", "Write", "PowerShell")
CODES = (("SHELL_WRITE", "refused"), ("EOL_CONVERTED", "fixed"), ("TOUCHED_BY_SHELL", "warning"),
         ("ANCHOR_NOT_FOUND", "warning"), ("POWERSHELL_TRAP", "refused"))


def week(folder: Path, seed: int = 7) -> None:
    """Seven days of sessions, each a mix of hook calls, check decisions, io tool calls and one bug, written
    the way the plugin writes them."""
    chance = random.Random(seed)
    telemetry = Telemetry(folder)
    for day in range(7):
        for number in range(12):
            session = f"s{day}-{number}"
            when = NOW - timedelta(days=day, minutes=number * 7)
            for call in range(20):
                tool = chance.choice(TOOLS)
                trace = TraceContext(f"{session}-{call:02d}".ljust(32, "0"), "0" * 16, None)
                base = dict(session=session, surface="mcp_hook", platform="win32", project="game", tool=tool,
                            trace=trace, cmd_head="sed -i 's/a/b/' x.txt" if tool == "Bash" else None)
                for event in ("PreToolUse", "PostToolUse"):
                    telemetry.record(TelemetryEvent(ts=when, event=event, latency_ms=chance.uniform(1, 90),
                                                    **base))
                if call % 5 == 0:
                    code, severity = chance.choice(CODES)
                    telemetry.record(TelemetryEvent(ts=when, event="PreToolUse", check="shell.writes",
                                                    code=code, severity=severity, **base))
            telemetry.record(TelemetryEvent(ts=when, session=session, event="tools/call", surface="mcp_tool",
                                            platform="win32", project="game", tool="io.edit",
                                            latency_ms=chance.uniform(2, 40), file_ext=".cpp", bytes=900))
            telemetry.record(TelemetryEvent(ts=when, session=session, event="PostToolUse", surface="mcp_hook",
                                            platform="win32", check="verify.write", code="GUARD_ERROR",
                                            severity="warning", error="KeyError 0123456789ab"))


class AWeekFitsOneScreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = Path(tempfile.mkdtemp(prefix="ioguard-report-"))
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        week(cls.folder)

    def test_the_week_merges_every_session_across_the_month(self):
        since = NOW - timedelta(days=7)
        paths = report.files([self.folder], since)
        found = report.summarise(paths, since)
        months = {path.parent.name for path in paths}
        self.assertEqual((months, len(found.sessions), found.events["tools/call"]),
                         ({"2026-09", "2026-10"}, 84, 84),
                         "D13: one file per session, in the month folder of its first line")
        self.assertEqual(sum(found.codes["GUARD_ERROR"].values()), 84, "every GUARD_ERROR is counted")

    def test_the_report_fits_one_screen_and_names_what_matters(self):
        text = report.run([self.folder], 7, NOW)
        lines = text.splitlines()
        self.assertEqual((len(lines) <= 45, max(map(len, lines)) <= report.WIDTH), (True, True),
                         f"a week fits one screen, 45 lines of 110 characters:\n{text}")
        for words in ("84 sessions", "SHELL_WRITE", "Hook call: p50", "io tool call: p50",
                      "One tool use, all its hooks", "Refused most: sed -i", "verify.write: KeyError"):
            with self.subTest(words=words):
                self.assertIn(words, text, "counts, times, refusal shapes and each GUARD_ERROR")

    def test_days_before_the_period_are_left_out(self):
        since = NOW - timedelta(days=1, hours=12)
        found = report.summarise(report.files([self.folder], since), since)
        self.assertEqual(len(found.sessions), 24, "the last day and a half hold the sessions of two days")

    def test_the_counts_a_tool_result_may_carry_hold_no_command_or_error_text(self):
        since = NOW - timedelta(days=7)
        carried = json.dumps(report.summarise(report.files([self.folder], since), since).counts())
        self.assertEqual(("sed -i" in carried, "KeyError" in carried, "game" in carried),
                         (False, False, False),
                         "a tool result lands in the model's context, so it takes counts and percentiles")


class EveryLineEndsWhole(unittest.TestCase):
    def test_names_past_the_width_are_counted_never_cut(self):
        found = report.Report(lines=1, first=NOW, last=NOW)
        found.events.update({f"PostToolUseFailureOf{number}": 100 - number for number in range(12)})
        found.projects.update({f"project-with-a-long-name-{number}": 10 for number in range(9)})
        lines = report.render(found, 1).splitlines()
        for line in (lines[1], lines[3]):
            with self.subTest(line=line):
                self.assertTrue(len(line) <= report.WIDTH and (line.endswith("more") or line[-1].isdigit()),
                                "a line ends on a count or on how many were left out, never inside a name")

    def test_an_info_code_is_counted_in_its_own_column(self):
        found = report.Report(lines=1, first=NOW, last=NOW)
        found.codes["EXIT_BENIGN"]["info"] += 3
        lines = report.render(found, 1).splitlines()
        header = next(line for line in lines if line.startswith("Code"))
        row = next(line for line in lines if line.startswith("EXIT_BENIGN"))
        self.assertEqual((header.split()[-1], row.split()[-1]), ("info", "3"),
                         "a code that fired shows its count")


class ALineIsReadAsWritten(unittest.TestCase):
    def test_a_broken_line_is_counted_and_skipped(self):
        folder = Path(tempfile.mkdtemp(prefix="ioguard-report-"))
        self.addCleanup(shutil.rmtree, folder, True)
        path = folder / "events" / "2026-10" / "s.jsonl"
        path.parent.mkdir(parents=True)
        good = TelemetryEvent(ts=NOW, session="s", event="PreToolUse", surface="mcp_hook", platform="darwin",
                              tool="Bash", latency_ms=4.0).to_json()
        path.write_bytes(json.dumps(good).encode() + b"\n{not json\n")
        found = report.summarise([path], NOW - timedelta(days=1))
        self.assertEqual((found.lines, found.unreadable, found.platforms["darwin"]), (1, 1, 1),
                         "a torn last line from a crash is counted, and the rest still reads")

    def test_every_code_a_run_gave_is_counted_once_and_so_is_each_fix(self):
        folder = Path(tempfile.mkdtemp(prefix="ioguard-report-"))
        self.addCleanup(shutil.rmtree, folder, True)
        results = (Result.of(Code.TOUCHED_BY_SHELL, "a.", "Bash", "win32"),
                   Result.of(Code.SHELL_WRITE, "b.", "Bash", "win32"))
        upper = rewriting("a.upper", "command", str.upper)
        says = saying("b.says", Verdict.ALLOW, results=results, layer=Layer.BYTES)
        pipeline_of(upper, says).run(bash_event("ls"), Context.fake(clock=FakeClock(NOW),
                                                                    telemetry=Telemetry(folder)))
        found = report.summarise(report.files([folder], NOW - timedelta(days=1)), NOW - timedelta(days=1))
        counted = {code: dict(severities) for code, severities in found.codes.items()}
        self.assertEqual(counted, {Code.TOUCHED_BY_SHELL.value: {"warning": 1},
                                   Code.SHELL_WRITE.value: {"refused": 1},
                                   Code.REWRITE_CONFLICT.value: {"fixed": 1}},
                         "both results count, and the rewrite counts once as fixed")
        self.assertEqual(len(found.hook_ms), 1, "the run's time is one hook call")

    def test_a_command_shape_is_its_program_and_its_option_or_subcommand(self):
        for command, expected in (("sed -i 's/a/b/' x", "sed -i"), ("git status --short", "git status"),
                                  ("C:/tools/python.exe script.py", "python.exe"), ("", "")):
            with self.subTest(command=command):
                self.assertEqual(report.shape(command), expected, "the shape names the program, never a path")


if __name__ == "__main__":
    unittest.main()
