"""lib.transcript finds the calls Claude Code refused before any hook ran, from the end of the transcript."""
import json
import unittest

from ioguard.lib.transcript import refusals


def use(call_id: str, name: str, given: dict) -> bytes:
    return json.dumps({"type": "assistant", "cwd": "C:/w", "message": {"content": [
        {"type": "tool_use", "id": call_id, "name": name, "input": given}]}}).encode()


def result(call_id: str, text, error: bool) -> bytes:
    return json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": error}]}}).encode()


def refused(text: str) -> str:
    return f"<tool_use_error>{text}</tool_use_error>"


class TheTrailingRefusalsAreFound(unittest.TestCase):
    def test_only_refusals_after_the_last_call_that_ran(self):
        parts = [{"type": "text", "text": refused("File has not been read")}]
        lines = [b'{"cut in half', use("u1", "Edit", {"old_string": "a"}),
                 result("u1", refused("gone"), True), use("u2", "Read", {}), result("u2", "1\tx", False),
                 use("u3", "Edit", {"old_string": "nine"}),
                 result("u3", refused("String to replace not found in file.\nString: nine"), True),
                 use("u4", "Write", {}), result("u4", parts, True)]
        found = refusals(b"\n".join(lines))
        self.assertEqual([(item.tool_use_id, item.tool, item.cwd) for item in found],
                         [("u3", "Edit", "C:/w"), ("u4", "Write", "C:/w")],
                         "the refusal before a call that ran is old, and a half line is skipped")
        self.assertEqual(found[0].error, "String to replace not found in file.\nString: nine",
                         "the error is the text inside <tool_use_error>")

    def test_an_error_while_running_is_not_a_refusal(self):
        lines = [use("u1", "Read", {}), result("u1", "File does not exist.", True)]
        self.assertEqual(refusals(b"\n".join(lines)), (), "a runtime failure reaches PostToolUseFailure")

    def test_a_result_whose_call_was_cut_off_is_skipped(self):
        self.assertEqual(refusals(result("gone", refused("x"), True)), (),
                         "the tool_use is needed to diagnose")


if __name__ == "__main__":
    unittest.main()
