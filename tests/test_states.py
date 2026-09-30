"""Each state io-guard passes between modules is an enum, turned into text only where it leaves as JSON or as
an MCP result, so a misspelt state fails where it is written."""
import json
import re
import unittest
from datetime import datetime, timezone

from ioguard.checks.registry import default_registry
from ioguard.cli import replay
from ioguard.hooks import answer
from ioguard.lib import code_tokens, config, heartbeat, indent, rules
from ioguard.lib.decisions import Decision, RewriteMode, Verdict
from ioguard.lib.events import PermissionMode, Tool
from ioguard.lib.platform import EVERY_PLATFORM, WINDOWS
from ioguard.lib.profile import IndentKind
from ioguard.mcp import tools_run
from tests import PLUGIN_SCRIPTS

PACKAGE = PLUGIN_SCRIPTS / "ioguard"
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def lines_matching(pattern: str, folder: str = "") -> list[str]:
    found = re.compile(pattern)
    return [f"{path.relative_to(PACKAGE).as_posix()}:{number}"
            for path in sorted((PACKAGE / folder).rglob("*.py"))
            for number, line in enumerate(path.read_bytes().decode("utf-8").splitlines(), 1)
            if found.search(line)]


class TheHarnessNamesRoundTrip(unittest.TestCase):
    def test_every_tool_and_permission_mode_reads_back_as_itself(self):
        for enum, fallback in ((Tool, Tool.OTHER), (PermissionMode, PermissionMode.UNKNOWN)):
            for member in enum:
                if member is not fallback:
                    with self.subTest(member=member):
                        self.assertIs(enum.named(member.value), member, "the harness's name is the member")


class EachStateIsAnEnum(unittest.TestCase):
    def test_a_rule_match_names_its_decision_and_a_wrapped_string_its_dialect(self):
        self.assertIs(rules.match_argv(rules.Rules(), ["git", "status"]).decision, rules.RuleVerdict.NONE,
                      "a command no rule meets has the decision NONE")
        self.assertIs(rules.wrapped(["bash", "-c", "echo x"]).dialect, rules.Dialect.BASH,
                      "bash -c's string is bash")

    def test_an_indent_style_is_the_profiles_indent_kind(self):
        cases = {"\tx\n": IndentKind.TABS, "  x\n": IndentKind.SPACES, "\tx\n  y\n": IndentKind.MIXED,
                 "x\n": IndentKind.NONE}
        for text, kind in cases.items():
            with self.subTest(text=text):
                self.assertIs(indent.style(text), kind, "one enum names an indent, whoever reads it")

    def test_a_comparison_names_its_mode(self):
        found = code_tokens.compare("int a;\n", "int a; // x\n", ".cpp", code_tokens.CompareMode.CODE)
        self.assertIs(found.how, code_tokens.CompareMode.CODE, "a comparison says how it compared")
        self.assertEqual([mode.value for mode in code_tokens.CompareMode], ["code", "includes", "exact"],
                         "io.compare's mode argument takes these three words")

    def test_a_run_state_is_text_only_in_the_tools_result(self):
        self.assertEqual({state.value for state in tools_run.RunState},
                         {"running", "ended", "timed out", "stopped"}, "io.run's result says one of these")

    def test_the_heartbeat_carries_the_era_and_writes_its_value(self):
        beat = heartbeat.Heartbeat(1, "s", heartbeat.Era.MODERN, NOW, NOW)
        self.assertEqual(json.loads(beat.encode())["era"], "modern", "the file holds the era's word")
        self.assertIs(heartbeat.parse(beat.encode()).era, heartbeat.Era.MODERN,
                      "and reads back as the member")

    def test_a_rewrite_mode_carries_its_verdict(self):
        self.assertEqual({mode: mode.verdict for mode in RewriteMode},
                         {RewriteMode.REFUSE: Verdict.DENY, RewriteMode.ASK: Verdict.ASK,
                          RewriteMode.ALLOW: Verdict.ALLOW}, "each mode names the verdict a rewrite takes")
        self.assertEqual(config.REWRITE_MODES, tuple(mode.value for mode in RewriteMode),
                         "the config's choices are the enum's words")
        self.assertFalse(hasattr(answer, "MODE_VERDICTS"), "the hook reads the verdict from the mode")

    def test_a_replay_names_its_kind(self):
        self.assertIs(replay.kind_of(Decision("x", Verdict.DENY)), replay.Kind.REFUSE, "a refusal is REFUSE")


class EveryPlatformIsOneConstant(unittest.TestCase):
    def test_no_check_spells_a_platform(self):
        self.assertEqual(lines_matching(r'"win32"|"darwin"', "checks"), [],
                         "a check names its platforms through lib.platform")

    def test_the_checks_run_on_the_platforms_they_did(self):
        platforms = {check_id: check.meta.platforms for check_id, check in default_registry().classes.items()}
        self.assertEqual({check_id for check_id, found in platforms.items() if found != EVERY_PLATFORM},
                         {"win.paths"}, "win.paths alone runs on Windows only")
        self.assertEqual(platforms["win.paths"], frozenset({WINDOWS}), "and on Windows")


class NoStateIsComparedAsText(unittest.TestCase):
    def test_no_module_compares_a_state_to_a_literal(self):
        fields = r'(?:\.(?:decision|dialect|era|how)|\bstate|style\([^)]*\)) *(?:==|!=|in) *[("]'
        words = r'== "(?:deny|bash|mixed|modern)"'
        self.assertEqual(lines_matching(f"{fields}|{words}"), [], "a state is compared as its member")


if __name__ == "__main__":
    unittest.main()
