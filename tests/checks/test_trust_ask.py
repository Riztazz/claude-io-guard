"""trust.ask puts a project's commands to the user before io.trust approves them, io.trust approves only what
the hook asked about, and an approval holds until the commands change."""
import shutil
import tempfile
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.checks.trust_ask import TrustAsk
from ioguard.lib import trust
from ioguard.lib.context import Context, LiveFs
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import detect
from ioguard.lib.results import Code, callable_name
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_trust import TrustInput, approve
from ioguard.mcp.toolspec import ToolCall, ToolFailure
from tests.support import events
from tests.support.project import TemporaryProject

HELD = {"verify": {".py": ["python", "tools/check.py", "{file}"]}}


class TrustTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-trust-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def context(self, project: Path, held: dict) -> Context:
        return Context.fake(platform=detect(), fs=LiveFs(), data_dir=self.home, project=project, held=held)

    def asked(self, ctx: Context, project: Path, tool: str = callable_name("io.trust")):
        registry = Registry()
        registry.register(TrustAsk)
        raw = events.pre_tool_use(tool, {}, project)
        return Pipeline(registry).run(Event.from_hook_json(raw, Surface.MCP_HOOK, ctx.platform), ctx)


class TheUserIsAskedFirst(TrustTest):
    def test_the_prompt_names_each_command_and_a_script_the_project_holds(self):
        with TemporaryProject({"tools/check.py": b"print(1)\n"}) as project:
            ctx = self.context(project, HELD)
            outcome = self.asked(ctx, project)
        result = outcome.decisions[0].results[0]
        self.assertEqual((outcome.verdict, result.code, ctx.session.asked),
                         (Verdict.ASK, Code.TRUST_ASKED,
                          {events.TOOL_USE_ID: (trust.fingerprint(HELD), ctx.clock.now())}),
                         "io.trust waits for the user's yes, and the hook records what it asked")
        self.assertIn("verify .py: python tools/check.py {file}", result.message, "each command is listed")
        self.assertIn("runs tools/check.py from inside the project", result.message,
                      "a script a pull can change is named")

    def test_nothing_waiting_or_another_tool_asks_nothing(self):
        with TemporaryProject() as project:
            cases = {"nothing waiting": (self.context(project, {}), callable_name("io.trust")),
                     "another tool": (self.context(project, HELD), callable_name("io.run"))}
            for name, (ctx, tool) in cases.items():
                with self.subTest(name):
                    self.assertEqual(self.asked(ctx, project, tool).verdict, Verdict.OBSERVE,
                                     "only io.trust with commands waiting asks")


class OnlyWhatTheHookAskedIsApproved(TrustTest):
    def test_no_prompt_approves_nothing_and_a_prompt_approves_those_commands(self):
        with TemporaryProject() as project:
            ctx = self.context(project, HELD)
            call = ToolCall(lambda: ctx, CancelToken(), project, None, tool_use_id=events.TOOL_USE_ID)
            with self.assertRaises(ToolFailure) as unasked:
                approve(TrustInput(), call)
            before = trust.approved(self.home, project, HELD)
            self.asked(ctx, project)
            done = approve(TrustInput(), call)
            after = trust.approved(self.home, project, HELD)
            changed = trust.approved(self.home, project, {"verify": {".py": ["python", "other.py"]}})
        self.assertEqual((unasked.exception.result.code, before), (Code.TRUST_ASKED, False),
                         "a call no prompt asked about approves nothing, so the model cannot approve alone")
        self.assertEqual((done.approved, after, changed), (True, True, False),
                         "the user's yes approves exactly those commands, and a changed one waits again")

    def test_a_declined_trust_ask_lets_no_other_call_approve(self):
        with TemporaryProject() as project:
            ctx = self.context(project, HELD)
            self.asked(ctx, project)
            for other in ("toolu_02OTHER", None):
                with self.subTest(tool_use_id=other):
                    call = ToolCall(lambda: ctx, CancelToken(), project, None, tool_use_id=other)
                    with self.assertRaises(ToolFailure, msg="a call no hook saw approves nothing"):
                        approve(TrustInput(), call)
            self.assertFalse(trust.approved(self.home, project, HELD), "nothing is approved")


if __name__ == "__main__":
    unittest.main()
