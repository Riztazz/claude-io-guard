"""Replay runs each recorded call through the pipeline, offline, and counts what each check would do."""
import unittest
from dataclasses import replace
from pathlib import Path

from ioguard.checks.registry import Registry
from ioguard.cli import replay
from ioguard.cli.corpus import Record
from tests.support import injected
from tests.support.project import TemporaryProject

CORPUS = Path("corpus")


def record(number: int, command: str, failed: bool = False, labels: tuple = ()) -> Record:
    return Record(id=f"toolu_{number}", project="P", session="s1", agent=False, ts="", version=None,
                  cwd="C:\\project", permission_mode="default", tool="Bash", input={"command": command},
                  failed=failed, result="Exit code 2" if failed else "ok", result_chars=2, labels=labels,
                  response=None if failed else {"stdout": "ok", "stderr": ""})


def registry_of(*names: str) -> Registry:
    registry = Registry()
    for name in names:
        registry.register(injected.CHECKS[name])
    return registry


class TheReportCountsEachCheck(unittest.TestCase):
    def test_refusals_split_by_whether_the_recorded_call_ran(self):
        records = [record(1, f"echo {injected.REFUSE}"), record(2, f"echo {injected.REFUSE}", failed=True,
                                                                labels=("unexpected-eof",)), record(3, "ls")]
        report = replay.replay(records, registry_of("refuse"), CORPUS)
        tally = report["checks"]["test.refuse"]
        self.assertEqual(tally["refuse"], {"ok": 1, "failed": 1},
                         "one refusal of a call that ran, and one of a call that failed")
        self.assertEqual(tally["false_positive_candidates"], 1, "the refused call that ran is a candidate")
        self.assertEqual(tally["labels"], {"unexpected-eof": 1},
                         "the labels of the calls it acted on are counted")

    def test_a_false_positive_candidate_is_sampled_for_review(self):
        report = replay.replay([record(1, f"echo {injected.REFUSE}")], registry_of("refuse"), CORPUS)
        sample = report["checks"]["test.refuse"]["samples"][0]
        self.assertEqual((sample["id"], sample["input"]), ("toolu_1", f"echo {injected.REFUSE}"),
                         "the sample names the call and shows its command")
        self.assertIn("IOGUARD_ALLOWED", sample["reason"], "and the refusal's reason, fix included")

    def test_the_sample_stays_at_its_cap_and_repeats_for_the_same_corpus(self):
        records = [record(number, f"echo {injected.REFUSE} {number}") for number in range(replay.SAMPLE * 3)]
        first = replay.replay(records, registry_of("refuse"), CORPUS)["checks"]["test.refuse"]
        second = replay.replay(records, registry_of("refuse"), CORPUS)["checks"]["test.refuse"]
        self.assertEqual(len(first["samples"]), replay.SAMPLE, "the sample never grows past its cap")
        self.assertEqual(first["samples"], second["samples"], "the same corpus gives the same sample")

    def test_fixes_and_warnings_are_counted_on_every_event(self):
        records = [record(1, f"echo {injected.ORIGINAL}"), record(2, "ls", failed=True)]
        report = replay.replay(records, registry_of("rewrite", "note", "output"), CORPUS)
        checks = report["checks"]
        self.assertEqual(checks["test.rewrite"]["fix"], {"ok": 1}, "the rewrite counts as a fix")
        self.assertEqual(checks["test.note"]["events"],
                         {"PreToolUse": 2, "PostToolUse": 1, "PostToolUseFailure": 1},
                         "each record runs before and after its call, the failure as PostToolUseFailure")
        self.assertEqual(checks["test.output"]["warn"], {"ok": 1},
                         "a replaced output on a call that ran is a warn")

    def test_a_check_that_raises_is_counted_and_the_replay_goes_on(self):
        report = replay.replay([record(1, "ls"), record(2, "pwd")], registry_of("broken", "note"), CORPUS)
        self.assertEqual(report["checks"]["test.broken"]["raised"], 4, "two records, two events each")
        self.assertEqual(report["checks"]["test.note"]["warn"], {"ok": 4}, "the other check ran every time")


class TheReportHasOneShape(unittest.TestCase):
    def test_the_report_keys_are_the_fixed_schema(self):
        report = replay.replay([record(1, "ls")], Registry(), CORPUS)
        self.assertEqual(set(report), {"schema", "corpus", "projects", "checks_run", "records", "unreadable",
                                       "seconds", "by_tool", "by_label", "checks"},
                         "task 31 reads these keys, so they change only with the schema number")
        self.assertEqual((report["records"], report["by_tool"]), (1, {"Bash": {"ok": 1}}),
                         "the corpus counts come with the report")

    def test_the_text_says_when_no_check_ran(self):
        text = replay.render(replay.replay([record(1, "ls")], Registry(), CORPUS))
        self.assertIn("none, so every count below is zero", text, "an empty registry is said, not implied")

    def test_nothing_is_written_during_a_replay(self):
        replayed = replay.Replay(registry_of("refuse"))
        replayed.run(record(1, f"echo {injected.REFUSE}"))
        ctx = replayed.context(record(1, "ls"))
        self.assertEqual((ctx.fs.writes, ctx.telemetry.enabled), ([], False),
                         "the file system is in memory and telemetry is off")


class AShellResultIsReplayedAsTheModelSawIt(unittest.TestCase):
    def test_a_call_recorded_without_a_response_carries_its_result_as_stdout(self):
        recorded = replace(record(1, "ls"), response=None, result="a.txt\nb.txt")
        after = list(replay.Replay(Registry()).events(recorded))[1]
        self.assertEqual(after.tool_response, {"stdout": "a.txt\nb.txt"},
                         "an older release kept only the text the model read")

    def test_the_saved_output_is_read_from_disk_while_it_is_there(self):
        with TemporaryProject({"tool-results/b1.txt": b"1\n2\n"}) as root:
            saved = root / "tool-results" / "b1.txt"
            notice = f"<persisted-output>\nOutput too large (1KB). Full output saved to: {saved}"
            recorded = replace(record(1, "seq 2"), response=None, result=notice)
            ctx = replay.Replay(Registry()).context(recorded)
            self.assertEqual(ctx.fs.read_bytes(saved), b"1\n2\n", "the check reads the file as it would live")
        gone = replay.Replay(Registry()).context(recorded)
        self.assertEqual(gone.fs.files, {}, "a file deleted since leaves the file system empty")


if __name__ == "__main__":
    unittest.main()
