"""Rewrites compose on disjoint fields, chain on shared ones, and an exclusive rewrite drops the later one."""
import unittest

from ioguard.lib.decisions import Decision, Rewrite, RewriteError, Verdict, apply_one, compose
from ioguard.lib.results import Code


def setting(check_id: str, key: str, value: str, exclusive: bool = False) -> Rewrite:
    return Rewrite(check_id, frozenset({key}), lambda given: {**given, key: value}, f"{check_id} set {key}",
                   Code.REWRITE_CONFLICT, exclusive)


def appending(check_id: str, key: str, tail: str) -> Rewrite:
    return Rewrite(check_id, frozenset({key}), lambda given: {**given, key: given[key] + tail}, "",
                   Code.REWRITE_CONFLICT)


class RewritesCompose(unittest.TestCase):
    def test_rewrites_on_disjoint_fields_both_apply(self):
        result = compose([setting("a", "command", "x"), setting("b", "description", "y")],
                         {"command": "c", "description": "d"})
        self.assertEqual(dict(result.tool_input), {"command": "x", "description": "y"},
                         "two rewrites on different fields both apply")

    def test_rewrites_on_a_shared_field_chain_in_order(self):
        result = compose([appending("a", "command", "-1"), appending("b", "command", "-2")], {"command": "c"})
        self.assertEqual(result.tool_input["command"], "c-1-2",
                         "the second rewrite of a shared field sees the first one's output")

    def test_an_exclusive_rewrite_drops_the_later_one_on_its_field(self):
        first = setting("a", "content", "x", exclusive=True)
        second = setting("b", "content", "y")
        result = compose([first, second], {"content": "c"})
        self.assertEqual((result.tool_input["content"], result.conflicts[0].dropped.check_id),
                         ("x", "b"), "an exclusive rewrite owns its field and the later rewrite is dropped")

    def test_a_rewrite_that_changes_an_undeclared_field_is_a_bug(self):
        sneaky = Rewrite("a", frozenset({"command"}), lambda given: {**given, "description": "z"}, "",
                         Code.REWRITE_CONFLICT)
        with self.assertRaisesRegex(RewriteError, "description"):
            apply_one(sneaky, {"command": "c", "description": "d"})

    def test_compose_leaves_the_given_input_unchanged(self):
        given = {"command": "c"}
        compose([setting("a", "command", "x")], given)
        self.assertEqual(given, {"command": "c"}, "compose never mutates the input it is given")


class VerdictsOrder(unittest.TestCase):
    def test_deny_outranks_ask_outranks_allow_outranks_observe(self):
        self.assertEqual(max(Verdict.ALLOW, Verdict.DENY, Verdict.OBSERVE, Verdict.ASK), Verdict.DENY,
                         "the merged verdict is the strongest one")

    def test_observe_says_nothing(self):
        decision = Decision.observe("x")
        self.assertEqual((decision.verdict, decision.results, decision.rewrite), (Verdict.OBSERVE, (), None),
                         "an observing decision carries no result and no rewrite")


if __name__ == "__main__":
    unittest.main()
