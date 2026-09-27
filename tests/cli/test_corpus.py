"""The corpus pairs each guarded tool call in a transcript with its result, and keeps its whole input."""
import json
import unittest
from pathlib import Path

from ioguard.cli import corpus
from tests.support import transcripts as tx
from tests.support.project import TemporaryProject


def built(entries: list, extra: bytes = b"", sidechain: list | None = None) -> tuple[list, dict]:
    with TemporaryProject() as root:
        folder = root / "projects" / "one"
        tx.write(folder / f"{tx.SESSION}.jsonl", entries, extra)
        if sidechain:
            tx.write(folder / tx.SESSION / "subagents" / "agent-a.jsonl", sidechain)
        index = corpus.build([("One", folder)], root / "corpus")
        return list(corpus.load(root / "corpus")), index


class ACallMeetsItsResult(unittest.TestCase):
    def test_a_bash_call_keeps_its_input_result_mode_and_response(self):
        response = {"stdout": "hi", "stderr": "", "interrupted": False}
        records, _ = built([tx.prompt("go", mode="acceptEdits"),
                            tx.tool_use("toolu_1", "Bash", {"command": "echo hi", "timeout": 60000}),
                            tx.tool_result("toolu_1", "hi", response=response)])
        record = records[0]
        self.assertEqual((record.tool, record.input, record.result, record.response),
                         ("Bash", {"command": "echo hi", "timeout": 60000}, "hi", response),
                         "the record holds the whole input, the result and the structured response")
        self.assertEqual((record.permission_mode, record.cwd, record.version, record.project),
                         ("acceptEdits", tx.CWD, "2.1.283", "One"),
                         "the mode comes from the last prompt, and the cwd and version from the call")

    def test_a_failed_edit_is_labelled_with_its_error_class(self):
        miss = "<tool_use_error>String to replace not found in file."
        records, index = built([tx.tool_use("toolu_2", "Edit", {"file_path": "a", "old_string": "x",
                                                                "new_string": "y"}),
                                tx.tool_result("toolu_2", miss, failed=True)])
        self.assertEqual((records[0].failed, records[0].labels), (True, ("not-found",)),
                         "the failure and its label travel with the record")
        self.assertEqual(index["labels"], {"not-found": 1}, "the index counts every label")

    def test_a_subagents_call_is_marked(self):
        records, _ = built([], sidechain=[tx.tool_use("toolu_3", "Read", {"file_path": "a"}),
                                          tx.tool_result("toolu_3", "1\tone")])
        self.assertEqual([(record.id, record.agent) for record in records], [("toolu_3", True)],
                         "a call from a subagent transcript is in the corpus and says so")


class WhatTheCorpusLeavesOut(unittest.TestCase):
    def test_a_tool_io_guard_does_not_guard_is_left_out(self):
        records, _ = built([tx.tool_use("toolu_4", "TodoWrite", {"todos": []}),
                            tx.tool_result("toolu_4", "ok")])
        self.assertEqual(records, [], "only the file and shell tools enter the corpus")

    def test_a_call_with_no_result_and_a_broken_line_are_counted_and_dropped(self):
        records, index = built([tx.tool_use("toolu_5", "Bash", {"command": "sleep 9"})],
                               extra=b'{"tool_result": broken\n')
        self.assertEqual((records, index["unpaired"], index["unreadable"]), ([], 1, 1),
                         "a call cut off by the session's end and a line that is not JSON are counted")

    def test_long_results_are_cut_and_the_length_kept(self):
        long = "x" * (corpus.RESULT_CHARS + 50)
        response = {"stdout": "y" * (corpus.RESPONSE_CHARS + 50),
                    "lines": list(range(corpus.RESPONSE_ITEMS + 5))}
        records, _ = built([tx.tool_use("toolu_6", "Bash", {"command": "cat big"}),
                            tx.tool_result("toolu_6", long, response=response)])
        record = records[0]
        self.assertEqual((len(record.result), record.result_chars), (corpus.RESULT_CHARS, len(long)),
                         "the result keeps its head and its full length")
        self.assertEqual((len(record.response["stdout"]), len(record.response["lines"])),
                         (corpus.RESPONSE_CHARS, corpus.RESPONSE_ITEMS),
                         "long strings and lists in the response are cut")

    def test_the_corpus_file_is_ascii_json_lines(self):
        with TemporaryProject() as root:
            folder = root / "p"
            written = {"file_path": "a", "content": chr(0x17C)}
            tx.write(folder / "s.jsonl", [tx.tool_use("u", "Write", written), tx.tool_result("u", "ok")])
            corpus.build([("P", folder)], root / "out")
            data = (root / "out" / "P.jsonl").read_bytes()
        self.assertTrue(data.isascii(), "non-ASCII content is escaped, so the file reads the same everywhere")
        self.assertEqual(json.loads(data)["input"]["content"], chr(0x17C), "and it decodes back exact")


if __name__ == "__main__":
    unittest.main()
