"""transport.body moves a heredoc or python -c body into a file when the Bash tool would cut the command or
halve its backslashes, refuses what cannot move, and leaves a short command untouched."""
import unittest
from dataclasses import replace
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.checks.session_probe import WINDOWS_CUT
from ioguard.checks.shell_writes import ShellWrites
from ioguard.checks.transport_body import TransportBody, budget_for
from ioguard.hooks.answer import answer
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context, Probe
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code
from tests.support import events

CWD = Path("C:/project")
SCRATCH = Path("C:/scratch")
WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)
BIG_BODY = "".join(f"print('line {number:04d} of the moved body')\n" for number in range(300))


def context(platform: Platform = WINDOWS, **overrides) -> Context:
    windows = platform.windows
    probe = replace(Probe.unprobed(platform), transport_budget=WINDOWS_CUT if windows else None,
                    halving=True if windows else None)
    return Context.fake(**({"config": defaults(), "platform": platform, "probe": probe} | overrides))


def run(command: str, ctx: Context | None = None, scratchpad: Path | None = SCRATCH):
    """The pipeline's outcome with transport.body alone, for a Bash call in the given context."""
    ctx = ctx or context()
    raw = events.bash(command, CWD)
    raw["scratchpad_dir"] = "" if scratchpad is None else str(scratchpad)
    registry = Registry()
    registry.register(ShellWrites)          # transport.body runs after it, and the fake git tracks nothing
    registry.register(TransportBody)
    event = Event.from_hook_json(raw, Surface.MCP_HOOK, ctx.platform)
    return event, Pipeline(registry).run(event, ctx), ctx


def moved_by(outcome):
    """transport.body's own decision in the outcome."""
    return next(decision for decision in outcome.decisions if decision.check_id == "transport.body")


def heredoc(body: str, delimiter: str = "'PY'") -> str:
    return f"python - <<{delimiter}\n{body}PY\n"


class AShortCommandRunsUntouched(unittest.TestCase):
    def test_a_short_heredoc_without_a_pair_of_backslashes_is_left_alone(self):
        _, outcome, ctx = run(heredoc("print(1)\n"))
        self.assertEqual((outcome.verdict, outcome.rewrites, ctx.fs.writes), (Verdict.OBSERVE, (), []),
                         "nothing moves and nothing is written, so default mode asks nothing")

    def test_macos_has_no_cut_and_no_halving(self):
        _, outcome, _ = run(heredoc(BIG_BODY * 3 + "print(r'\\\\n')\n"), context(MACOS))
        self.assertEqual((outcome.verdict, outcome.rewrites), (Verdict.OBSERVE, ()),
                         "on macOS the probe records no cut, so even a long body stays")


class ABodyMovesToAFile(unittest.TestCase):
    def test_a_long_quoted_heredoc_moves_and_the_command_reads_it(self):
        command = heredoc(BIG_BODY)
        _, outcome, ctx = run(command)
        path = ctx.fs.writes[0]
        self.assertEqual(outcome.tool_input["command"], f'python - < "{path.as_posix()}"\n',
                         "the heredoc becomes a stdin redirect from the file")
        self.assertEqual(ctx.fs.files[path], BIG_BODY.encode("utf-8"),
                         "the file holds the body byte for byte")
        self.assertEqual(path.parent, SCRATCH / "io-guard", "the file goes in the session scratchpad")
        self.assertEqual(outcome.rewrites[0].code, Code.BODY_MOVED_TO_FILE, "the rewrite reports its code")
        self.assertIn("KB heredoc body to", outcome.rewrites[0].note, "the note says what moved and where")

    def test_a_short_body_with_a_pair_of_backslashes_moves_on_windows(self):
        _, outcome, ctx = run(heredoc("print(len(r'\\\\n'))\n"))
        self.assertEqual(ctx.fs.files[ctx.fs.writes[0]], b"print(len(r'\\\\n'))\n",
                         "both backslashes reach the file, which the Bash tool would have halved")
        self.assertEqual(len(outcome.rewrites), 1, "a halving hazard moves even a short body")

    def test_a_python_c_body_with_a_pair_moves_to_a_py_file(self):
        _, outcome, ctx = run("python -c 'import re; print(re.sub(r\"\\\\s\", \"\", \"a b\"))'")
        path = ctx.fs.writes[0]
        self.assertEqual(path.suffix, ".py", "an inline python body gets a .py file")
        self.assertIn(f'open("{path.as_posix()}"', outcome.tool_input["command"],
                      "the -c argument now runs the file")

    def test_the_same_body_gets_the_same_file(self):
        _, first, one = run(heredoc(BIG_BODY))
        _, second, two = run(heredoc(BIG_BODY))
        self.assertEqual(one.fs.writes, two.fs.writes, "the file is named by the body's hash")

    def test_the_data_folder_serves_when_the_event_has_no_scratchpad(self):
        ctx = context(data_dir=Path("C:/data"))
        _, outcome, ctx = run(heredoc(BIG_BODY), ctx, scratchpad=None)
        self.assertEqual(ctx.fs.writes[0].parent, Path("C:/data/bodies"), "the body goes to the data folder")

    def test_a_moved_command_moves_nothing_the_second_time(self):
        _, first, ctx = run(heredoc(BIG_BODY))
        _, second, _ = run(first.tool_input["command"], ctx)
        self.assertEqual((second.rewrites, second.verdict), ((), Verdict.OBSERVE),
                         "the fixed point: the moved command has no body left to move")


class WhatCannotMoveIsRefused(unittest.TestCase):
    def test_a_long_unquoted_heredoc_is_refused_with_transport_budget(self):
        _, outcome, ctx = run(heredoc(BIG_BODY, "PY"))
        result = moved_by(outcome).results[0]
        self.assertEqual((outcome.verdict, result.code), (Verdict.DENY, Code.TRANSPORT_BUDGET),
                         "bash expands an unquoted body, so moving it would change it")
        self.assertIn("Write tool", result.render(), "the fix says to write the script and run the file")
        self.assertEqual(ctx.fs.writes, [], "nothing is written for a refusal")

    def test_a_pair_outside_any_body_is_a_warning_and_the_call_runs(self):
        _, outcome, _ = run("sed 's/\\\\n/ /' notes.txt")
        result = moved_by(outcome).results[0]
        self.assertEqual((outcome.verdict, result.code), (Verdict.ALLOW, Code.BACKSLASH_TRANSPORT),
                         "agents double backslashes to survive the halving, so a refusal would stop 1% of "
                         "calls that ran (D25)")
        self.assertIn("s/", outcome.context[0], "the model reads where the pair is")

    def test_a_pair_left_after_the_move_is_warned_about_next_to_the_move(self):
        _, outcome, _ = run("sed 's/\\\\n/ /' f && " + heredoc(BIG_BODY))
        decision = moved_by(outcome)
        self.assertEqual((decision.rewrite.code, decision.results[0].code),
                         (Code.BODY_MOVED_TO_FILE, Code.BACKSLASH_TRANSPORT),
                         "the heredoc moves, and the sed argument it cannot fix is named")

    def test_a_pair_before_a_double_quote_is_left_alone(self):
        _, outcome, _ = run('echo "{\\\\\\"k\\\\\\": 1}"')
        self.assertEqual(outcome.verdict, Verdict.OBSERVE,
                         "measured: a run before a double quote arrives whole")

    def test_with_nowhere_to_write_a_long_body_is_refused(self):
        _, outcome, _ = run(heredoc(BIG_BODY), scratchpad=None)
        self.assertEqual(moved_by(outcome).results[0].code, Code.TRANSPORT_BUDGET,
                         "no scratchpad and no data folder means no move")


class TheBudget(unittest.TestCase):
    def test_the_smallest_of_the_key_the_cut_and_the_override_applies(self):
        command = heredoc("x = 1\n" * 500, "PY")          # 3,000 bytes and unquoted, so it cannot move
        narrowed_config = Config(defaults().values | {"transport.budget_bytes": 2000})
        _, narrowed, _ = run(command, context(config=narrowed_config))
        overridden = context()
        overridden.session.budget_override = 1000
        _, learned, _ = run(command, overridden)
        _, default, _ = run(command)
        self.assertEqual((narrowed.verdict, learned.verdict, default.verdict),
                         (Verdict.DENY, Verdict.DENY, Verdict.OBSERVE),
                         "2,000 from the key and 1,000 learned both refuse what 6,000 lets through")

    def test_a_budget_learned_where_the_probe_found_no_cut_applies(self):
        ctx = context(MACOS)
        self.assertIsNone(budget_for(ctx), "no cut probed and none learned, so no budget")
        ctx.session.budget_override = 9000
        self.assertEqual(budget_for(ctx), 6000, "a learned cut brings the budget key's margin with it")
        ctx.session.budget_override = 4000
        self.assertEqual(budget_for(ctx), 4000, "and a lower learned cut wins")


class TheAnswerFollowsTheMode(unittest.TestCase):
    def test_refuse_mode_gives_the_moved_command_as_the_fix(self):
        event, outcome, ctx = run(heredoc(BIG_BODY))
        reply = answer(event, outcome, "refuse")["hookSpecificOutput"]
        self.assertEqual(reply["permissionDecision"], "deny", "auto and dontAsk refuse the rewrite")
        self.assertIn("Run this command instead, exactly as written:\npython - < ",
                      reply["permissionDecisionReason"], "the model reruns the moved command")
        self.assertTrue(ctx.fs.writes, "the file the fix names exists already")


if __name__ == "__main__":
    unittest.main()
