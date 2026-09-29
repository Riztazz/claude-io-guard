"""The tools/ scripts run the cli commands end to end: transcripts to a report, and one command or file
checked offline."""
import json
import os
import subprocess
import sys
import unittest

from tests import REPO
from tests.support import transcripts as tx
from tests.support.project import TemporaryProject

PROBE = {"os": sys.platform, "bash": {"path": "bash", "version": "5.2"}, "pwsh": None,
         "python": {"path": "python", "version": "3.14.0"}, "git": None, "console_encoding": "utf-8",
         "fs_case_insensitive": False, "transport_budget": 6000, "halving": False,
         "claude_code_version": "2.1.283", "dirty_at_start": [], "taken_at": "2026-09-28T12:00:00+00:00"}


def run(script: str, *args: str, cwd, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO / "tools" / script), *args], cwd=cwd, capture_output=True,
                          timeout=120, env=env)


def with_home(home) -> dict[str, str]:
    return {**os.environ, "IOGUARD_HOME": str(home)}


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

    def test_report_html_writes_a_page_file(self):
        with TemporaryProject() as root:
            (root / "home" / "events").mkdir(parents=True)
            done = run("report.py", "--data", str(root / "home"), "--html", "stats.html", cwd=root)
            page = (root / "stats.html").read_bytes()
        self.assertEqual((done.returncode, b"window.IOGUARD_STATIC" in page), (0, True),
                         f"the file holds the page and its data: {done.stderr!r}")

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


class TheCheckCommandRunsTheChecksAndNothingElse(unittest.TestCase):
    def test_a_sed_in_place_on_a_tracked_file_is_refused_and_the_file_is_untouched(self):
        with TemporaryProject({"a.txt": b"one\n"}, git=True) as root, TemporaryProject() as home:
            done = run("ioguard.py", "check", "sed -i s/one/two/ a.txt", "--cwd", str(root), cwd=root,
                       env=with_home(home))
            kept = (root / "a.txt").read_bytes()
        self.assertEqual(done.returncode, 1, f"a refusal exits 1: {done.stderr!r}")
        self.assertIn(b"SHELL_WRITE", done.stdout, "the refusal names its code")
        self.assertEqual(kept, b"one\n", "the command never runs")

    def test_a_heredoc_over_the_budget_is_moved_and_no_file_is_written(self):
        body = "\n".join(f"line {n} of the body" for n in range(400))
        with TemporaryProject() as root, TemporaryProject({"probe.json": json.dumps(PROBE).encode()}) as home:
            done = run("ioguard.py", "check", f"cat > out.txt <<'EOF'\n{body}\nEOF", cwd=root,
                       env=with_home(home))
            written = sorted(path.name for path in [*root.rglob("*"), *home.rglob("*")])
        self.assertEqual(done.returncode, 0, f"a moved body runs: {done.stderr!r}")
        self.assertIn(b"BODY_MOVED_TO_FILE", done.stdout, "the move names its code")
        self.assertIn(b"It would run as:", done.stdout, "and prints the command as it would run")
        self.assertEqual(written, ["probe.json"], "the body, the telemetry and out.txt stay unwritten")

    def test_a_folder_that_is_not_there_is_named(self):
        with TemporaryProject() as root:
            done = run("ioguard.py", "check", "ls", "--cwd", str(root / "missing"), cwd=root)
        self.assertEqual(done.returncode, 1, "a missing folder fails")
        self.assertIn(b"Name the folder the command runs from with --cwd", done.stdout, "and names the fix")


class TheProfileCommandPrintsWhatARead(unittest.TestCase):
    def test_a_crlf_file_with_a_bom_is_profiled_as_such(self):
        with TemporaryProject({"a.txt": b"\xef\xbb\xbfone\r\n    two\r\n"}) as root:
            done = run("ioguard.py", "profile", "a.txt", cwd=root)
        self.assertEqual(done.returncode, 0, f"profile exits 0: {done.stderr!r}")
        self.assertEqual(done.stdout.decode("ascii").strip(), "a.txt: CRLF, BOM, UTF-8, 4 spaces, 2 lines",
                         "the line names the endings, the BOM, the indent and the count")

    def test_a_file_that_is_not_there_is_named(self):
        with TemporaryProject() as root:
            done = run("ioguard.py", "profile", "missing.txt", cwd=root)
        self.assertEqual((done.returncode, done.stdout.strip()), (1, b"missing.txt is not a file."),
                         "a missing file fails and says so")


if __name__ == "__main__":
    unittest.main()
