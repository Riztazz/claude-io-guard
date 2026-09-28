"""The pipeline orders checks, chains their rewrites, drops a conflict, stops on a refusal, holds the time
budget, fails open on a check that raises, and merges what they decided."""
import unittest
from pathlib import Path

from ioguard.checks.base import Cost
from ioguard.checks.pipeline import Budget, Pipeline
from ioguard.checks.registry import Registry
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.results import Code, Layer, Result
from tests.support import events
from tests.support.checks import make_check


def bash_event(command: str = "ls") -> Event:
    return Event.from_hook_json(events.bash(command, Path("C:/p")), Surface.COMMAND_HOOK)


def pipeline_of(*check_classes, budget: Budget = Budget()) -> Pipeline:
    registry = Registry()
    for check_class in check_classes:
        registry.register(check_class)
    return Pipeline(registry, budget)


def rewriting(check_id: str, key: str, change, exclusive: bool = False):
    """A check that rewrites one field when change alters it, and observes otherwise."""
    def decide(check, event, ctx):
        after = change(event.tool_input.get(key))
        if after == event.tool_input.get(key):
            return Decision.observe(check_id)
        rewrite = Rewrite(check_id, frozenset({key}), lambda given: {**given, key: change(given.get(key))},
                          f"{check_id} rewrote {key}", Code.REWRITE_CONFLICT, exclusive)
        return Decision(check_id, Verdict.ALLOW, rewrite=rewrite, context=(f"{check_id} ran",))
    return make_check(check_id, decide, writes=(key,))


def saying(check_id: str, verdict: Verdict, seen: list | None = None, **fields):
    def decide(check, event, ctx):
        if seen is not None:
            seen.append((check_id, event.command))
        return Decision(check_id, verdict, **fields)
    return make_check(check_id, decide, **{key: fields.pop(key) for key in ("layer", "cost", "after")
                                            if key in fields})


def waiting(check_id: str, milliseconds: float, cost: Cost = Cost.CHEAP):
    def decide(check, event, ctx):
        ctx.clock.advance(milliseconds)
        return Decision(check_id, Verdict.ALLOW, context=(check_id,))
    return make_check(check_id, decide, cost=cost)


class PipelineOrders(unittest.TestCase):
    def test_checks_run_by_layer_then_cost_then_id(self):
        seen = []
        checks = [saying("z.bytes", Verdict.ALLOW, seen, layer=Layer.BYTES),
                  saying("b.transport", Verdict.ALLOW, seen, layer=Layer.TRANSPORT, cost=Cost.MEDIUM),
                  saying("a.transport", Verdict.ALLOW, seen, layer=Layer.TRANSPORT),
                  saying("c.location", Verdict.ALLOW, seen, layer=Layer.LOCATION)]
        pipeline_of(*checks).run(bash_event(), Context.fake())
        self.assertEqual([check_id for check_id, _ in seen],
                         ["c.location", "a.transport", "b.transport", "z.bytes"],
                         "location runs first, then transport by cost, then bytes")

    def test_after_moves_a_check_behind_the_one_it_names(self):
        seen = []
        first = saying("m.first", Verdict.ALLOW, seen, layer=Layer.BYTES)
        early = saying("a.early", Verdict.ALLOW, seen, layer=Layer.LOCATION, after=("m.first",))
        pipeline_of(first, early).run(bash_event(), Context.fake())
        self.assertEqual([check_id for check_id, _ in seen], ["m.first", "a.early"],
                         "a check runs after every check its after set names, whatever its layer")


class PipelineChainsRewrites(unittest.TestCase):
    def test_a_later_check_sees_the_rewritten_input(self):
        seen = []
        upper = rewriting("a.upper", "command", str.upper)
        watcher = saying("b.watch", Verdict.OBSERVE, seen, layer=Layer.BYTES)
        outcome = pipeline_of(upper, watcher).run(bash_event("ls -la"), Context.fake())
        self.assertEqual((seen, outcome.tool_input["command"]), ([("b.watch", "LS -LA")], "LS -LA"),
                         "the running input carries each rewrite to the checks that follow")

    def test_rewrites_on_different_fields_both_apply(self):
        upper = rewriting("a.upper", "command", str.upper)
        describe = rewriting("b.describe", "description", lambda value: "described")
        outcome = pipeline_of(upper, describe).run(bash_event("ls"), Context.fake())
        result = (outcome.tool_input["command"], outcome.tool_input["description"], len(outcome.rewrites))
        self.assertEqual(result, ("LS", "described", 2), "disjoint rewrites compose")

    def test_a_conflict_on_an_exclusive_field_is_dropped_with_rewrite_conflict(self):
        ctx = Context.fake()
        owner = rewriting("a.owner", "command", lambda value: "echo owned", exclusive=True)
        second = rewriting("b.second", "command", lambda value: value + " --second")
        outcome = pipeline_of(owner, second).run(bash_event("ls"), ctx)
        self.assertEqual(outcome.tool_input["command"], "echo owned", "the exclusive rewrite keeps its field")
        self.assertTrue(any(line.startswith(f"{Code.REWRITE_CONFLICT.value}:") for line in outcome.context),
                        "the dropped rewrite is reported to the model as REWRITE_CONFLICT")
        self.assertIn(Code.REWRITE_CONFLICT.value, [item.code for item in ctx.telemetry.events],
                      "every dropped rewrite is telemetry")


class PipelineStopsOnARefusal(unittest.TestCase):
    def test_nothing_runs_after_a_deny(self):
        seen = []
        refuse = saying("a.refuse", Verdict.DENY, seen, layer=Layer.LOCATION)
        later = saying("b.later", Verdict.ALLOW, seen, layer=Layer.BYTES)
        outcome = pipeline_of(refuse, later).run(bash_event(), Context.fake())
        self.assertEqual(([check_id for check_id, _ in seen], outcome.verdict), (["a.refuse"], Verdict.DENY),
                         "the first refusal ends the run, and the verdict is DENY")


class PipelineHoldsTheBudget(unittest.TestCase):
    def test_past_the_soft_limit_only_expensive_checks_are_skipped(self):
        ctx = Context.fake()
        slow = waiting("a.slow", 350)
        expensive = waiting("b.expensive", 0, cost=Cost.EXPENSIVE)
        cheap = waiting("c.cheap", 0)
        outcome = pipeline_of(slow, expensive, cheap).run(bash_event(), ctx)
        self.assertEqual((outcome.skipped, outcome.context), (("b.expensive",), ("a.slow", "c.cheap")),
                         "past 300 ms the check that starts a program is skipped, and a cheap one still runs")
        self.assertIn(Code.BUDGET_EXCEEDED.value, [item.code for item in ctx.telemetry.events],
                      "each skip is BUDGET_EXCEEDED in telemetry")

    def test_past_the_hard_limit_every_check_is_skipped(self):
        slow = waiting("a.slow", 2100)
        cheap = waiting("b.cheap", 0)
        outcome = pipeline_of(slow, cheap).run(bash_event(), Context.fake())
        self.assertEqual((outcome.skipped, outcome.verdict), (("b.cheap",), Verdict.ALLOW),
                         "past 2,000 ms every remaining check is skipped and the call goes ahead")

    def test_the_budget_comes_from_the_config(self):
        from ioguard.lib import config
        values = {**config.defaults().values, "pipeline.soft_ms": 50}
        ctx = Context.fake(config=config.Config(values))
        outcome = Pipeline(pipeline_of(waiting("a.slow", 60), waiting("b.x", 0, Cost.EXPENSIVE)).registry
                           ).run(bash_event(), ctx)
        self.assertEqual(outcome.skipped, ("b.x",), "pipeline.soft_ms sets the soft limit")


class PipelineFailsOpen(unittest.TestCase):
    def test_a_check_that_raises_is_skipped_and_named_once_per_session(self):
        def explode(check, event, ctx):
            raise KeyError("bug")
        ctx = Context.fake()
        broken = make_check("a.broken", explode)
        after = saying("b.after", Verdict.ALLOW, context=("after ran",))
        pipeline = pipeline_of(broken, after)
        with self.assertLogs("ioguard.pipeline", "WARNING") as logged:
            first = pipeline.run(bash_event(), ctx)
            second = pipeline.run(bash_event(), ctx)
        self.assertEqual((first.errors, first.context), (("a.broken",), ("after ran",)),
                         "the pipeline logs the broken check and goes on to the next")
        self.assertTrue(first.user_message.startswith(f"{Code.GUARD_ERROR.value}:"),
                        "the first failure is named to the user as GUARD_ERROR")
        self.assertIsNone(second.user_message, "the same check failing again says nothing more")
        self.assertIn("KeyError", logged.output[0], "the traceback goes to the debug log")

    def test_a_rewrite_that_touches_an_undeclared_field_fails_open(self):
        def sneaky(check, event, ctx):
            rewrite = Rewrite("a.sneaky", frozenset({"command"}),
                              lambda given: {**given, "description": "changed"}, "", Code.REWRITE_CONFLICT)
            return Decision("a.sneaky", Verdict.ALLOW, rewrite=rewrite)
        with self.assertLogs("ioguard.pipeline", "WARNING"):
            check = make_check("a.sneaky", sneaky, writes=("command",))
            outcome = pipeline_of(check).run(bash_event(), Context.fake())
        self.assertEqual((outcome.errors, outcome.tool_input["description"]),
                         (("a.sneaky",), "Run a command"),
                         "a rewrite outside its declared fields is a bug, and the input stays untouched")

    def test_a_rewrite_of_a_field_missing_from_meta_writes_fails_open(self):
        def undeclared(check, event, ctx):
            rewrite = Rewrite("a.quiet", frozenset({"command"}), lambda given: {**given, "command": "x"},
                              "", Code.REWRITE_CONFLICT)
            return Decision("a.quiet", Verdict.ALLOW, rewrite=rewrite)
        with self.assertLogs("ioguard.pipeline", "WARNING") as logged:
            outcome = pipeline_of(make_check("a.quiet", undeclared)).run(bash_event("ls"), Context.fake())
        self.assertEqual((outcome.errors, outcome.tool_input["command"]), (("a.quiet",), "ls"),
                         "a check rewrites only the fields its CheckMeta.writes declares")
        self.assertIn("CheckMeta.writes", logged.output[0], "the log names the missing declaration")


class PipelineMerges(unittest.TestCase):
    def test_the_verdict_is_the_strongest_and_context_keeps_order(self):
        ask = saying("a.ask", Verdict.ASK, context=("one",))
        allow = saying("b.allow", Verdict.ALLOW, context=("two",), layer=Layer.BYTES)
        outcome = pipeline_of(ask, allow).run(bash_event(), Context.fake())
        self.assertEqual((outcome.verdict, outcome.context), (Verdict.ASK, ("one", "two")),
                         "the merged verdict is the strongest, and context lines keep the run order")

    def test_only_the_first_output_replacement_counts(self):
        first = saying("a.first", Verdict.ALLOW, output_replacement={"stdout": "first"})
        second = saying("b.second", Verdict.ALLOW, output_replacement={"stdout": "second"}, layer=Layer.BYTES)
        outcome = pipeline_of(first, second).run(bash_event(), Context.fake())
        self.assertEqual(outcome.output_replacement, {"stdout": "first"}, "one output replacement at most")

    def test_results_of_a_decision_reach_the_outcome(self):
        result = Result.of(Code.BUDGET_EXCEEDED, "x.", "Bash", "win32")
        outcome = pipeline_of(saying("a.says", Verdict.ALLOW, results=(result,))).run(bash_event(),
                                                                                      Context.fake())
        self.assertEqual(outcome.decisions[0].results, (result,), "a decision's results reach the outcome")


class PipelineRecordsEveryCode(unittest.TestCase):
    def test_each_result_of_a_decision_is_its_own_line_and_only_the_first_is_timed(self):
        ctx = Context.fake()
        results = (Result.of(Code.TOUCHED_BY_SHELL, "a.", "Bash", "win32"),
                   Result.of(Code.SHELL_WRITE, "b.", "Bash", "win32"))
        pipeline_of(saying("a.says", Verdict.ALLOW, results=results)).run(bash_event(), ctx)
        lines = [(item.code, item.latency_ms is not None) for item in ctx.telemetry.events
                 if item.check == "a.says"]
        self.assertEqual(lines, [(Code.TOUCHED_BY_SHELL.value, True), (Code.SHELL_WRITE.value, False)],
                         "a code given second is recorded, and the check's time is counted once")


class PipelineReachesAFixedPoint(unittest.TestCase):
    def test_running_on_its_own_output_changes_nothing(self):
        strip = rewriting("a.strip", "command", lambda value: value.rstrip())
        upper = rewriting("b.upper", "command", str.upper)
        pipeline = pipeline_of(strip, upper)
        first = pipeline.run(bash_event("ls -la   "), Context.fake())
        again = pipeline.run(bash_event(first.tool_input["command"]), Context.fake())
        self.assertEqual((first.tool_input["command"], again.rewrites, again.verdict), ("LS -LA", (),
                                                                                       Verdict.OBSERVE),
                         "a rewrite recognises its own output, so a second run rewrites nothing")


if __name__ == "__main__":
    unittest.main()
