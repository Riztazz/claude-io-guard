"""verify.command runs the user's verify command on a written file and hands its output to the agent, and a
project file can never name one."""
import json
import os
import sys
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest import mock

from ioguard.checks import verify_command
from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import detect
from ioguard.lib.proc import RunResult
from ioguard.lib.results import Code, Severity
from tests.support import events
from tests.support.project import TemporaryProject

REGISTRY = default_registry()
COMPILE = [sys.executable, "-m", "py_compile", "{file}"]
MARK = [sys.executable, "-c", "import sys; open(sys.argv[1] + '.ran', 'w').close()", "{file}"]


def after_write(project: Path, name: str, verify: dict, ctx: Context | None = None, **options):
    """The PostToolUse outcome of a Write of name in project, with verify as the user's commands."""
    values = {**defaults(REGISTRY.keys()).values, "verify": verify}
    values.update({f"checks.verify.command.{key}": value for key, value in options.items()})
    ctx = ctx or Context.fake(config=Config(MappingProxyType(values)), platform=detect(),
                              env=dict(os.environ))
    raw = events.post_tool_use("Write", {"file_path": str(project / name), "content": ""}, {}, project)
    return Pipeline(REGISTRY).run(Event.from_hook_json(raw, Surface.MCP_HOOK, detect()), ctx)


def lines(outcome) -> tuple[str, ...]:
    """The first line of verify.command's message and the rest, or () when it said nothing."""
    results = next((decision.results for decision in outcome.decisions
                    if decision.check_id == "verify.command"), ())
    return tuple(results[0].message.split("\n", 1)) if results else ()


class TheCommandRuns(unittest.TestCase):
    def test_a_failing_command_hands_its_output_to_the_agent(self):
        with TemporaryProject({"bad.py": b"def f(:\n"}) as project:
            found = lines(after_write(project, "bad.py", {".py": COMPILE}))
        self.assertIn("and it exited 1:", found[0], "the first line names the command and its exit code")
        self.assertIn("SyntaxError", found[1], "the compiler's own message follows")

    def test_what_the_command_said_carries_a_code_the_telemetry_counts(self):
        with TemporaryProject({"bad.py": b"def f(:\n"}) as project:
            outcome = after_write(project, "bad.py", {".py": COMPILE})
        result = next(decision.results[0] for decision in outcome.decisions
                      if decision.check_id == "verify.command")
        self.assertEqual((result.code, result.severity, result.evidence["exit_code"]),
                         (Code.VERIFY_OUTPUT, Severity.WARNING, 1), "a warning with a code the report counts")

    def test_a_passing_quiet_command_adds_nothing(self):
        with TemporaryProject({"good.py": b"x = 1\n"}) as project:
            outcome = after_write(project, "good.py", {".py": COMPILE})
        self.assertEqual(lines(outcome), (), "a pass with no output says nothing")

    def test_no_command_for_the_extension_runs_nothing(self):
        with TemporaryProject({"a.txt": b"x\n"}) as project:
            after_write(project, "a.txt", {".py": MARK})
            self.assertFalse((project / "a.txt.ran").exists(), "only the named extension runs its command")

    def test_long_output_is_cut_to_the_limit(self):
        noisy = [sys.executable, "-c", "print('x' * 50)", "{file}"]
        with TemporaryProject({"a.py": b""}) as project:
            found = lines(after_write(project, "a.py", {".py": noisy}, output_chars=10))
        self.assertEqual(found[1], "x" * 10 + "\n[40 more characters]", "the agent sees the head and a count")

    def test_a_timeout_and_a_missing_program_are_named(self):
        cases = {"stopped the verify command": RunResult((), None, b"", b"", True, 0.2),
                 "could not start": RunResult((), None, b"", b"", False, 0.0, start_error="not found")}
        for words, result in cases.items():
            with self.subTest(words), TemporaryProject({"a.py": b""}) as project, \
                    mock.patch.object(verify_command.proc, "run", return_value=result):
                self.assertIn(words, lines(after_write(project, "a.py", {".py": COMPILE}))[0],
                              "the agent learns the check did not finish")


class OnlyTheUserNamesACommand(unittest.TestCase):
    def test_a_project_file_that_sets_verify_runs_nothing(self):
        files = {"a.py": b"x = 1\n", ".claude/io-guard.json": json.dumps({"verify": {".py": MARK}}).encode()}
        with TemporaryProject(files) as project:
            ctx = Context.live(None, project, REGISTRY.keys())
            outcome = after_write(project, "a.py", {}, ctx=ctx)
            self.assertEqual((ctx.config_report.dropped, (project / "a.py.ran").exists(), outcome.verdict),
                             ((project / ".claude" / "io-guard.json",), False, Verdict.OBSERVE),
                             "the project file is dropped whole, and its command never starts (D24)")

    def test_the_users_own_config_runs_its_command(self):
        user = json.dumps({"verify": {".py": MARK}}).encode()
        with TemporaryProject({"a.py": b"x = 1\n", "data/config.json": user}) as project:
            after_write(project, "a.py", {}, ctx=Context.live(project / "data", project, REGISTRY.keys()))
            self.assertTrue((project / "a.py.ran").exists(),
                            "the user's config.json names the command, and it runs")


if __name__ == "__main__":
    unittest.main()
