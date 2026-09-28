"""The measurement counts the baseline's classes before and after io-guard by the same rules, per 1,000 calls,
and gives a verdict only when the period after has calls enough to judge."""
import unittest

from ioguard.cli import measure
from ioguard.cli.corpus import Record

SCRIPT = "C:/Users/me/AppData/Local/Temp/claude/x/scratchpad/fix.py"


def call(number: int, day: str, tool: str = "Bash", labels: tuple[str, ...] = (), **given) -> Record:
    return Record(id=f"toolu_{number}", project="p", session="s", agent=False, ts=f"{day}T10:00:00Z",
                  version="2.1.283", cwd="C:/p", permission_mode="default", tool=tool, input=given,
                  failed=False, result="", result_chars=0, response=None, labels=labels)


def period(day: str, calls: int, **counted: tuple[str, ...]) -> list[Record]:
    """calls records on day, the first ones carrying the labels each class names, one call per label set."""
    made, number = [], 0
    for tool, labels in counted.items():
        made.append(call(number, day, tool.split("_")[0], labels))
        number += 1
    return made + [call(number + index, day) for index in range(calls - len(made))]


class BothPeriodsCountByTheSameRules(unittest.TestCase):
    def test_each_class_counts_per_thousand_calls_on_either_side_of_the_day(self):
        before = period("2026-09-01", 2000, Bash_a=("unexpected-eof",), Edit_b=("not-found",),
                        Write_c=("not-read-yet",), Bash_d=("git-eol",))
        after = period("2026-10-01", 1000, Bash_a=("heredoc-eof",))
        found = measure.measure([*before, *after], "2026-09-28")
        self.assertEqual([(side.calls, side.rate("Bash commands failing in transport")) for side in found],
                         [(2000, 0.5), (1000, 1.0)], "a transport failure counts on the side of its day")
        self.assertEqual((found[0].rate("Edit anchor misses"), found[0].rate("Git LF and CRLF warnings")),
                         (0.5, 0.5), "each class from its own label")

    def test_a_scratchpad_script_that_writes_counts_once_by_its_path(self):
        writes = "open('out.txt', 'w').write(x)"
        records = [call(1, "2026-09-01", "Write", file_path=SCRIPT, content=writes),
                   call(2, "2026-09-02", "Write", file_path=SCRIPT, content=writes),
                   call(3, "2026-09-02", "Write", file_path=SCRIPT.replace("fix", "read"),
                        content="print(1)"),
                   call(4, "2026-09-02", "Write", file_path="C:/p/src/a.py", content=writes)]
        before, _ = measure.measure(records, "2026-09-28")
        self.assertEqual(before.count("New scratchpad scripts that write files"), 1,
                         "one script written twice is one script, and a script that only reads is none")


class AVerdictNeedsCallsEnough(unittest.TestCase):
    def test_too_few_calls_after_give_no_verdict_and_enough_give_one(self):
        before = period("2026-09-01", 2000, Edit_a=("not-found",), Edit_b=("not-found",))
        few = measure.measure([*before, *period("2026-10-01", 10)], "2026-09-28")
        enough = measure.measure([*before, *period("2026-10-01", 2000)], "2026-09-28")
        anchors = measure.MEASURES[1]
        self.assertEqual((measure.verdict(anchors, *few), measure.verdict(anchors, *enough)),
                         ("too few calls", "met"), "10 calls judge nothing, and a drop to 0 meets 50% lower")

    def test_the_table_names_each_measure_its_target_and_the_hook_time(self):
        text = measure.render(*measure.measure(period("2026-09-01", 5), "2026-09-28"), 86.0)
        for words in ("Edit anchor misses", "at least 80% lower", "Hook latency p95", "86 ms", "per 1,000"):
            with self.subTest(words=words):
                self.assertIn(words, text, "every row of task 31's table")


if __name__ == "__main__":
    unittest.main()
