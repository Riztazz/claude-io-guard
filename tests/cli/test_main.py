"""tools/corpus.py and tools/replay.py run the cli commands end to end, from transcripts to a report."""
import json
import subprocess
import sys
import unittest

from tests import REPO
from tests.support import transcripts as tx
from tests.support.project import TemporaryProject


def run(script: str, *args: str, cwd) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "tools" / script), *args], cwd=cwd, capture_output=True,
                          timeout=120)


class TheToolsRunTheCommands(unittest.TestCase):
    def test_a_transcript_becomes_a_corpus_and_then_a_report(self):
        with TemporaryProject() as root:
            tx.write(root / "t" / "s.jsonl", [tx.tool_use("u1", "Bash", {"command": "echo hi"}),
                                             tx.tool_result("u1", "hi")])
            built = run("corpus.py", f"Demo={root / 't'}", "--out", "c", cwd=root)
            replayed = run("replay.py", "--corpus", "c", "--out", "r.json", cwd=root)
            report = json.loads((root / "r.json").read_bytes())
        self.assertEqual((built.returncode, replayed.returncode), (0, 0), f"both exit 0: {replayed.stderr!r}")
        self.assertIn(b"Wrote 1 records", built.stdout, "the corpus command says what it wrote")
        self.assertEqual((report["records"], report["projects"]), (1, ["Demo"]),
                         "the report covers the corpus")

    def test_replay_with_no_corpus_says_how_to_build_one(self):
        with TemporaryProject() as root:
            done = run("replay.py", "--corpus", "missing", cwd=root)
        self.assertEqual(done.returncode, 1, "replay without a corpus fails")
        self.assertIn(b"Build one with the corpus command first", done.stdout, "and names the fix")

    def test_a_source_that_is_not_name_equals_folder_is_refused(self):
        with TemporaryProject() as root:
            done = run("corpus.py", str(root), cwd=root)
        self.assertEqual(done.returncode, 2, "argparse refuses the argument")
        self.assertIn(b"is not NAME=FOLDER", done.stderr, "and says what shape it wants")


if __name__ == "__main__":
    unittest.main()
