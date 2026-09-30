"""hooks.answer shapes an Outcome into the JSON Claude Code documents for each event and rewrite mode."""
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.hooks.answer import answer
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Surface
from ioguard.lib.results import Code, Layer, Result
from tests.support import events, injected
from tests.support.checks import make_check

CWD = Path.cwd()


def outcome_of(raw: dict, *check_classes):
    registry = Registry()
    for check_class in check_classes:
        registry.register(check_class)
    event = Event.from_hook_json(raw, Surface.COMMAND_HOOK)
    return event, Pipeline(registry).run(event, Context.fake())


def answered(raw: dict, *check_classes, mode: str = "ask") -> dict:
    event, outcome = outcome_of(raw, *check_classes)
    return answer(event, outcome, mode)


def saying(check_id: str, verdict: Verdict, layer: Layer = Layer.TRANSPORT, **fields):
    return make_check(check_id, lambda check, event, ctx: Decision(check_id, verdict, **fields), layer=layer)


def describing(check_id: str = "d.describe"):
    """A check that rewrites the Bash description, a field other than the command."""
    swap = Rewrite(check_id, frozenset({"description"}), lambda given: {**given, "description": "fixed"},
                   "The description was fixed.", Code.REWRITE_CONFLICT)
    return make_check(check_id, lambda check, event, ctx: Decision(check_id, Verdict.ALLOW, rewrite=swap),
                      writes=("description",))


def content_fix(check_id: str = "w.content"):
    swap = Rewrite(check_id, frozenset({"content"}), lambda given: {**given, "content": "one\r\n"},
                   "The line endings were kept.", Code.REWRITE_CONFLICT)
    return make_check(check_id, lambda check, event, ctx: Decision(check_id, Verdict.ALLOW, rewrite=swap),
                      writes=("content",))


class APreToolUseAnswerFollowsTheVerdict(unittest.TestCase):
    def test_nothing_to_say_answers_an_empty_object(self):
        self.assertEqual(answered(events.bash("echo hi", CWD)), {},
                         "an empty pipeline answers {}, which lets the call go on untouched")

    def test_context_alone_answers_additional_context_and_no_permission_decision(self):
        reply = answered(events.bash("echo hi", CWD), injected.CHECKS["note"])["hookSpecificOutput"]
        self.assertEqual(set(reply), {"hookEventName", "additionalContext"},
                         "a line for the model never carries a permission decision, so no prompt is skipped")

    def test_a_refusal_puts_its_result_first_and_the_earlier_lines_after(self):
        before = saying("a.before", Verdict.ALLOW, layer=Layer.LOCATION, context=("earlier line",))
        reply = answered(events.bash(f"echo {injected.REFUSE}", CWD), before,
                         injected.CHECKS["refuse"])["hookSpecificOutput"]
        reason = reply["permissionDecisionReason"].splitlines()
        self.assertEqual(reply["permissionDecision"], "deny", "a refusing check denies the call")
        self.assertEqual((reason[0].split(":")[0], reason[1:]), ("GUARD_ERROR", ["earlier line"]),
                         "the refusal's result renders first, then the lines of the checks before it")

    def test_a_check_that_asks_answers_ask_with_its_lines_as_the_reason(self):
        reply = answered(events.bash("echo hi", CWD), saying("a.ask", Verdict.ASK, context=("look first",)),
                         mode="allow")["hookSpecificOutput"]
        self.assertEqual((reply["permissionDecision"], reply["permissionDecisionReason"]),
                         ("ask", "look first"), "an ask shows the user the check's lines")

    def test_an_ask_says_what_happens_and_ends_on_its_code_with_no_advice(self):
        result = Result.of(Code.RULE_ASKED, "io.run would run git push.", "Bash", "win32")
        reply = answered(events.bash("echo hi", CWD), saying("a.ask", Verdict.ASK, results=(result,)),
                         mode="allow")["hookSpecificOutput"]
        self.assertEqual(reply["permissionDecisionReason"], "io.run would run git push. (RULE_ASKED)",
                         "the user reads the prompt, so the code comes last and the model's advice stays out")

    def test_the_user_message_is_the_system_message(self):
        telling = saying("a.tell", Verdict.ALLOW, user_message="heads up")
        self.assertEqual(answered(events.bash("echo hi", CWD), telling)["systemMessage"], "heads up",
                         "a user message reaches the user as systemMessage")


class ARewriteFollowsTheMode(unittest.TestCase):
    def rewritten(self, mode: str, *more) -> dict:
        raw = events.bash(f"echo {injected.ORIGINAL}", CWD)
        return answered(raw, injected.CHECKS["rewrite"], *more, mode=mode)["hookSpecificOutput"]

    def test_each_mode_gives_its_permission_decision(self):
        for mode, decision in (("refuse", "deny"), ("ask", "ask"), ("allow", "allow")):
            with self.subTest(mode=mode):
                self.assertEqual(self.rewritten(mode)["permissionDecision"], decision,
                                 f"a rewrite in {mode} mode answers {decision}")

    def test_ask_and_allow_carry_the_rewritten_input_and_the_note(self):
        told = {"ask": ("permissionDecisionReason",
                        "io-guard changed how this call is written, and it does the same thing.\n"
                        "io-guard's test check rewrote the command. (REWRITE_CONFLICT)"),
                "allow": ("additionalContext",
                          "REWRITE_CONFLICT: io-guard's test check rewrote the command.")}
        for mode, (note_field, note) in told.items():
            with self.subTest(mode=mode):
                reply = self.rewritten(mode)
                self.assertEqual(reply["updatedInput"]["command"], f"echo {injected.REWRITTEN}",
                                 "updatedInput is the whole input after every rewrite")
                self.assertEqual(reply[note_field], note,
                                 "the user reads that the call does the same thing and the code last, and "
                                 "the model reads the code first")

    def test_refuse_names_the_changed_fields_when_the_command_is_not_the_one(self):
        reply = answered(events.bash("echo hi", CWD), describing(), mode="refuse")["hookSpecificOutput"]
        self.assertTrue(reply["permissionDecisionReason"].endswith(
            'Call Bash again with these fields: {"description": "fixed"}'),
            "refuse mode gives the model the changed fields to send again")

    def test_a_check_that_asks_outranks_allow_mode(self):
        reply = self.rewritten("allow", saying("z.ask", Verdict.ASK, layer=Layer.OUTPUT))
        self.assertEqual(reply["permissionDecision"], "ask", "a check's ask outranks the user's allow")

    def test_a_file_tool_rewrite_leaves_the_decision_to_the_harness(self):
        raw = events.write(CWD / "a.txt", "one\n", CWD)
        for mode in ("refuse", "ask", "allow"):
            with self.subTest(mode=mode):
                reply = answered(raw, content_fix(), mode=mode)["hookSpecificOutput"]
                self.assertEqual((reply.get("permissionDecision"), reply["updatedInput"]["content"]),
                                 (None, "one\r\n"),
                                 "the harness applies the conformed input and asks or approves as before")


class OtherEventsAnswerWithTheirFields(unittest.TestCase):
    def test_post_tool_use_carries_context_replaced_output_and_the_classifier_note(self):
        raw = events.post_tool_use("Bash", {"command": "echo hi"}, events.bash_result("hi\n"), CWD)
        reply = answered(raw, injected.CHECKS["note"], injected.CHECKS["output"])["hookSpecificOutput"]
        self.assertEqual(set(reply), {"hookEventName", "additionalContext", "updatedToolOutput",
                                      "classifierContext"}, "PostToolUse answers with its three fields")
        self.assertEqual(reply["updatedToolOutput"]["stdout"], injected.OUTPUT,
                         "the replaced output keeps the tool's shape with stdout changed")

    def test_post_tool_use_failure_and_session_start_carry_context_only(self):
        for raw in (events.post_tool_use_failure("Read", {"file_path": "x"}, "File does not exist.", CWD),
                    events.session_start(CWD)):
            with self.subTest(event=raw["hook_event_name"]):
                reply = answered(raw, injected.CHECKS["note"])["hookSpecificOutput"]
                self.assertEqual(set(reply), {"hookEventName", "additionalContext"},
                                 "these events answer with context lines only")

    def test_stop_has_no_hook_specific_output(self):
        event = Event.from_hook_json({"hook_event_name": "Stop", "session_id": "s", "cwd": str(CWD)},
                                     Surface.COMMAND_HOOK)
        outcome = Pipeline(Registry()).run(event, Context.fake())
        self.assertEqual(answer(event, outcome, "ask"), {}, "io-guard adds nothing to a Stop answer")
        self.assertIs(event.kind, HookEvent.STOP, "the event read as Stop")


if __name__ == "__main__":
    unittest.main()
