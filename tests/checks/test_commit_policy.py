"""commit.policy refuses a git commit whose message holds what the user's policy forbids, whether the message
arrives by -m, by -F, through a heredoc or in a PowerShell here-string, and refuses nothing by default."""
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks.commit_policy import CommitPolicy
from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, callable_name
from tests.support import events

PROJECT = Path("C:/project")
WINDOWS = Platform("win32", True)
POLICY = {"commit_policy.forbid": ["Co-Authored-By", "Generated with"], "commit_policy.ascii_only": True}
HEREDOC = ("git commit -m \"$(cat <<'EOF'\nfeat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\nEOF\n"
           ")\"")


def decided(tool: str, tool_input: dict, policy: dict | None = None, files: dict | None = None):
    config = Config(MappingProxyType({**defaults().values, **(POLICY if policy is None else policy)}))
    ctx = Context.fake(files or {}, platform=WINDOWS, config=config)
    registry = Registry()
    registry.register(CommitPolicy)
    raw = events.pre_tool_use(tool, tool_input, PROJECT)
    return Pipeline(registry).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx)


class AForbiddenMessageIsRefused(unittest.TestCase):
    def test_a_co_author_line_is_refused_however_the_message_arrives(self):
        cases = {"heredoc in -m": ("Bash", {"command": HEREDOC}, {}),
                 "-m": ("Bash", {"command": "git commit -am 'fix: y' -m 'co-authored-by: a <b@c>'"}, {}),
                 "-F file": ("Bash", {"command": "git commit -F msg.txt"},
                             {PROJECT / "msg.txt": b"feat: z\n\nCo-Authored-By: a <b@c>\n"}),
                 "-F - heredoc": ("Bash", {"command": "git commit -F - <<'EOF'\nfeat: w\n\nGenerated with "
                                                      "x\nEOF"}, {}),
                 "here-string": ("PowerShell", {"command": "git commit -m @'\nfeat: p\n\nGenerated with "
                                                           "x\n'@"}, {}),
                 "io.run": (callable_name("io.run"), {"argv": ["git", "commit", "-m", "Co-Authored-By: a"]},
                            {}),
                 "io.run bash -c": (callable_name("io.run"), {"argv": [
                     "bash", "-c", "git add . && git commit -m 'Co-Authored-By: a'"]}, {}),
                 "io.run bash body": (callable_name("io.run"), {"lang": "bash", "code": HEREDOC}, {}),
                 "io.run powershell body": (callable_name("io.run"), {"lang": "powershell", "code":
                                            "git commit -m @'\nfeat: p\n\nGenerated with x\n'@"}, {})}
        for name, (tool, tool_input, files) in cases.items():
            with self.subTest(name):
                outcome = decided(tool, tool_input, files=files)
                self.assertEqual((outcome.verdict, outcome.decisions[0].results[0].code),
                                 (Verdict.DENY, Code.COMMIT_POLICY), "the lead is the only author (rule 5)")

    def test_the_refusal_names_what_and_where_and_the_fix(self):
        result = decided("Bash", {"command": HEREDOC}).decisions[0].results[0]
        self.assertIn("Co-Authored-By on line 4", result.render(), "the model sees the text and its line")
        self.assertIn("commit again", result.fix.text, "and the call to make instead")

    def test_a_non_ascii_character_is_refused_when_the_policy_asks(self):
        outcome = decided("Bash", {"command": "git commit -m 'fix: a \u2014 b'"})
        self.assertIn("U+2014 on line 1", outcome.decisions[0].results[0].message,
                      "an em dash in a message the policy keeps ASCII")


class EverythingElseRuns(unittest.TestCase):
    def test_a_clean_message_and_other_commands_run(self):
        for command in ("git commit -m 'feat: plain'", "git status", "git log --grep Co-Authored-By",
                        "echo Co-Authored-By", "git -C sub commit -m 'fix: ok'"):
            with self.subTest(command=command):
                self.assertEqual(decided("Bash", {"command": command}).verdict, Verdict.OBSERVE,
                                 "only a commit message is read")

    def test_the_default_policy_refuses_nothing(self):
        self.assertEqual(decided("Bash", {"command": HEREDOC}, policy={}).verdict, Verdict.OBSERVE,
                         "a user who names no policy commits as before")

    def test_another_mcp_tool_is_left_alone(self):
        outcome = decided("mcp__other__tool", {"argv": ["git", "commit", "-m", "Co-Authored-By: a"]})
        self.assertEqual(outcome.verdict, Verdict.OBSERVE, "only io.run's argument list runs a program")


if __name__ == "__main__":
    unittest.main()
