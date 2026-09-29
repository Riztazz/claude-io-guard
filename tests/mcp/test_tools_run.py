"""io.run runs a program or a code body with no shell, under the user's rules, to its end or in the
background. io.status reports on the process, and io.read_log returns the new whole lines of a log, less the
noise."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from unittest import mock

from ioguard.checks.registry import default_registry
from ioguard.lib import runs
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context, LiveFs, ToolVersion
from ioguard.lib.platform import detect
from ioguard.lib.results import Code, Severity
from ioguard.mcp import handles
from ioguard.mcp.progress import CancelToken, ProgressReporter
from ioguard.mcp.tools_run import HandleInput, LogInput, RunInput, read_log, run, status
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolFailure
from tests.support.events import TOOL_USE_ID

BACKSLASHES = "print(len(r'\\\\n'), 'C:\\\\temp\\\\new', \"say \\\"hi\\\"\")\n"
RULES = {"permissions": {"deny": ["Bash(git push *)"], "ask": ["Bash(git fetch *)"]}}


class RunTest(unittest.TestCase):
    """A test with a project folder, a plugin data folder, a store of its own handles, and SETTINGS as the
    project's Claude Code settings."""
    SETTINGS: dict = {}

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ioguard-run-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.project = self.root / "project"
        (self.project / ".claude").mkdir(parents=True)
        (self.project / ".claude" / "settings.json").write_text(json.dumps(self.SETTINGS), encoding="utf-8")
        self.store = handles.HandleStore()
        patch = mock.patch.object(handles, "STORE", self.store)
        patch.start()
        self.addCleanup(patch.stop)

    def context(self, **values) -> Context:
        config = defaults(default_registry().keys())
        config = Config(MappingProxyType({**config.values, **values}))
        own = {key: value for key, value in os.environ.items() if key != "CLAUDE_CONFIG_DIR"}
        env = {**own, "CLAUDE_PROJECT_DIR": str(self.project), "USERPROFILE": str(self.root),
               "HOME": str(self.root)}
        ctx = Context.fake(config=config, fs=LiveFs(), data_dir=self.root / "data", platform=detect(),
                           env=env)
        return replace(ctx, probe=replace(ctx.probe, python=ToolVersion(sys.executable, "3.14")))

    def call(self, handler, given, ctx: Context, cancel: CancelToken | None = None,
             progress: ProgressReporter | None = None, tool_use_id: str | None = TOOL_USE_ID):
        return handler(given, ToolCall(lambda: ctx, cancel or CancelToken(), self.project, None, progress,
                                       tool_use_id=tool_use_id))

    def refusal(self, handler, given, ctx: Context, tool_use_id: str | None = TOOL_USE_ID):
        with self.assertRaises(ToolFailure) as failure:
            self.call(handler, given, ctx, tool_use_id=tool_use_id)
        return failure.exception.result


class AProgramRunsWithNoShell(RunTest):
    def test_a_code_body_runs_byte_for_byte(self):
        found = self.call(run, RunInput(lang="python", code=BACKSLASHES), self.context())
        body = next((self.root / "data" / "runs").rglob("body.py")).read_bytes()
        self.assertEqual((body, found.exit, found.tail), (BACKSLASHES.encode("utf-8"), 0,
                                                          ['3 C:\\temp\\new say "hi"']),
                         "SHW-2: the backslashes and quotes reach the file and the program as written")

    def test_an_exit_code_is_labelled_and_error_lines_are_named(self):
        (self.project / "a.txt").write_text("a\n")
        (self.project / "b.txt").write_text("b\n")
        diff = self.call(run, RunInput(argv=["git", "diff", "--no-index", "a.txt", "b.txt"]), self.context())
        self.assertEqual((diff.exit, diff.ok, diff.meaning),
                         (1, True, "the answer git diff --no-index gives when the inputs differ"),
                         "task 22's benign exits label a run as they label a Bash call")
        raised = self.call(run, RunInput(lang="python", code="raise ValueError('boom')\n"), self.context())
        self.assertEqual((raised.exit, raised.ok, [error.kind for error in raised.errors]),
                         (1, False, ["exception"]), "the lines that report errors come back with their kind")

    def test_an_error_line_in_a_long_log_is_numbered_from_the_files_start(self):
        program = "for n in range(1, 2001): print(f'step {n:04d}')\nprint('ValueError: boom')\n"
        found = self.call(run, RunInput(lang="python", code=program),
                          self.context(**{"checks.shell.results.max_bytes": 500}))
        self.assertEqual([error.line for error in found.errors], [2001],
                         "the line io.read_log gives, though only the log's last 500 bytes were read")

    def test_the_utf8_defaults_reach_the_program(self):
        program = "import os; print(os.environ['PYTHONUTF8'], os.environ['X'])"
        found = self.call(run, RunInput(argv=[sys.executable, "-c", program], env={"X": "given"}),
                          self.context())
        self.assertEqual(found.tail, ["1 given"], "task 10's variables and the call's own reach the program")

    def test_a_run_past_its_timeout_or_cancelled_is_stopped(self):
        sleeper = RunInput(argv=[sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1)
        self.assertEqual(self.call(run, sleeper, self.context()).state, "timed out",
                         "RUN-4: io-guard stops a run past its timeout")
        cancel = CancelToken()
        cancel.cancel()
        cancelled = self.call(run, replace(sleeper, timeout_s=60), self.context(), cancel)
        self.assertEqual(cancelled.state, "stopped", "a run the client cancels is stopped")

    def test_a_long_run_reports_progress_twice_a_second_at_most(self):
        sent = []
        slow = RunInput(argv=[sys.executable, "-c", "import time; time.sleep(1.3)"])
        self.call(run, slow, self.context(), progress=ProgressReporter(sent.append, "token"))
        self.assertTrue(1 <= len(sent) <= 3 and sent[0]["params"]["progressToken"] == "token",
                        "notifications/progress go out under the call's token, at most every half second")

    def test_arguments_that_do_not_make_one_program_are_refused(self):
        for given in (RunInput(), RunInput(argv=["x"], lang="python", code="1"),
                      RunInput(lang="cobol", code="1"), RunInput(argv=[sys.executable, "-c", "print(1)\x00"]),
                      RunInput(argv=[sys.executable, "-V"], env={"A=B": "1"}),
                      RunInput(lang="python", code="print('\ud800')")):
            with self.subTest(given=given):
                with self.assertRaises(InvalidArguments, msg="argv, or lang and code, one of them"):
                    self.call(run, given, self.context())


class TheUsersRulesHold(RunTest):
    SETTINGS = RULES

    def test_a_body_that_names_a_rules_program_asks(self):
        given = RunInput(lang="python", code="import subprocess\nsubprocess.run(['git', 'push'])")
        self.assertEqual(self.refusal(run, given, self.context()).code, Code.RULE_ASKED,
                         "no rule can see what a body does with git, so it runs only on the user's yes")
        self.assertEqual(self.call(run, RunInput(lang="python", code="print(1)"), self.context()).exit, 0,
                         "a body naming no rule's program runs")
    def test_a_deny_rule_refuses_the_run(self):
        result = self.refusal(run, RunInput(argv=["git", "push", "origin"]), self.context())
        self.assertEqual((result.code, result.severity), (Code.RULE_DENIED, Severity.REFUSED),
                         "D14: a Bash deny rule holds for io.run")

    def test_an_ask_rule_runs_only_what_the_hook_put_to_the_user(self):
        ctx = self.context()
        given = RunInput(argv=["git", "fetch", "--dry-run"])
        self.assertEqual(self.refusal(run, given, ctx).code, Code.RULE_ASKED,
                         "with no prompt from the hook, the command does not run")
        ctx.session.keep_ask(TOOL_USE_ID, runs.key({"argv": list(given.argv)}), ctx.clock.now())
        self.assertEqual(self.call(run, given, ctx).state, "ended", "after the hook asked, it runs")
        self.assertEqual(self.refusal(run, given, ctx).code, Code.RULE_ASKED,
                         "one answer lets one run through")

    def test_a_declined_run_ask_lets_no_other_call_run(self):
        ctx = self.context()
        given = RunInput(argv=["git", "fetch", "--dry-run"])
        ctx.session.keep_ask(TOOL_USE_ID, runs.key({"argv": list(given.argv)}), ctx.clock.now())
        for other in ("toolu_02OTHER", None):
            with self.subTest(tool_use_id=other):
                self.assertEqual(self.refusal(run, given, ctx, other).code, Code.RULE_ASKED,
                                 "the same command on a call no hook saw never runs on another call's ask")


class ABackgroundRunHasAHandle(RunTest):
    def test_status_reports_the_process_while_it_runs_and_its_end(self):
        ctx = self.context()
        started = self.call(run, RunInput(argv=[sys.executable, "-c", "import time; print('go', flush=True);"
                                                " time.sleep(1)"], background=True), ctx)
        running = self.call(status, HandleInput(started.handle), ctx)
        pump = self.store.get(started.handle, "run").payload["pump"]
        pump.wait(30)
        ended = self.call(status, HandleInput(started.handle), ctx)
        self.assertEqual((started.state, running.state, ended.state, ended.exit, ended.tail),
                         ("running", "running", "ended", 0, ["go"]),
                         "RUN-2: the state comes from the process, and the log gives the last lines")
        self.assertIsNotNone(self.store.get(started.handle, "run").expires,
                             "the handle's hour starts when the program ends")

    def test_an_unknown_or_expired_handle_is_handle_expired(self):
        result = self.refusal(status, HandleInput("no-such-handle"), self.context())
        self.assertEqual((result.code, result.fix.tool),
                         (Code.HANDLE_EXPIRED, "mcp__plugin_io-guard_io__io_run"),
                         "the fix starts the run again")

    def test_a_settled_handle_expires_after_its_ttl(self):
        now = [datetime(2026, 9, 28, tzinfo=timezone.utc)]
        store = handles.HandleStore(lambda: now[0])
        handle = store.create("run", {})
        store.settle(handle.id, timedelta(hours=1))
        now[0] += timedelta(minutes=59)
        self.assertEqual(store.get(handle.id, "run").id, handle.id, "the handle lives for its hour")
        now[0] += timedelta(minutes=2)
        with self.assertRaises(handles.HandleExpired, msg="past its hour the handle is gone"):
            store.get(handle.id, "run")
        self.assertEqual(store.sweep(), 1, "the sweep drops it")


class ALogIsReadAPartAtATime(RunTest):
    def write(self, data: bytes) -> Path:
        path = self.project / "build.log"
        with path.open("ab") as out:
            out.write(data)
        return path

    def test_each_call_returns_the_whole_lines_added_since_the_last(self):
        ctx = self.context()
        path = self.write(b"one\r\ntwo\nthr")
        first = self.call(read_log, LogInput("build.log"), ctx)
        self.write(b"ee\nfour\n")
        second = self.call(read_log, LogInput("build.log"), ctx)
        self.assertEqual((first.text, second.first_line, second.text),
                         ("     1| one\n     2| two", 3, "     3| three\n     4| four"),
                         "OUT-11: a half-written line waits until it ends")
        self.assertEqual(self.call(read_log, LogInput(str(path), since_line=1), ctx).first_line, 2,
                         "since_line starts after the line it names")

    def test_noise_is_dropped_and_a_shorter_log_starts_over(self):
        ctx = self.context(noise_patterns=["^LogTemp: Display:"])
        path = self.write(b"LogTemp: Display: x\nerror: y\n")
        found = self.call(read_log, LogInput("build.log"), ctx)
        self.assertEqual((found.text, found.dropped), ("     2| error: y", 1),
                         "noise_patterns leave lines out")
        path.write_bytes(b"new\n")
        again = self.call(read_log, LogInput("build.log"), ctx)
        self.assertEqual((again.text, bool(again.note)), ("     1| new", True),
                         "a log cut shorter is read from its start, and the result says so")

    def test_max_lines_leaves_the_rest_for_the_next_call(self):
        ctx = self.context(**{"io.read_log.max_lines": 2})
        self.write(b"a\nb\nc\n")
        first = self.call(read_log, LogInput("build.log"), ctx)
        self.assertEqual((first.last_line, first.more), (2, True), "the result says more lines wait")
        self.assertEqual(self.call(read_log, LogInput("build.log"), ctx).text, "     3| c",
                         "and the next call has them")


if __name__ == "__main__":
    unittest.main()
