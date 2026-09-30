"""The probe runner's verdicts tell a model that skipped the probe's step from io-guard failing it."""
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from ioguard.lib.editorconfig import properties
from ioguard.lib.folders import project_root
from ioguard.lib.git import Git
from tests.support.project import TemporaryProject

RUNNER = Path(__file__).resolve().parents[1] / "tools" / "probes" / "run_probe.py"
SPEC = importlib.util.spec_from_file_location("run_probe", RUNNER)
run_probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run_probe)


def written(line: str) -> dict:
    """A live-invisible summary whose strip.py holds line as its line 2, kept as the runner keeps bytes."""
    text = f"import io\n{line}\n"
    return {"claude": "2.1.283", "files": {"strip.py": text.encode("utf-8").decode("latin-1")}}


class ALiveInvisibleVerdict(unittest.TestCase):
    def test_a_write_with_no_invisible_character_is_no_verdict(self):
        with mock.patch.object(run_probe, "latest", lambda name: (Path("runs/20260929-173519"),
                                                                 written("raw = raw.lstrip('')"))):
            said = run_probe.verdict("live-invisible")
        self.assertTrue(said.startswith("no verdict"), "the model's miss is not io-guard's")
        self.assertIn("no invisible character", said, "and the line says why")

    def test_a_write_with_one_passes_when_the_model_read_its_name(self):
        summary = written(f"raw = raw.lstrip('{chr(0x200B)}')")
        named = mock.patch.object(run_probe, "context_reached",
                                  lambda name, needle: "[U+200B] on line 2" in needle)
        with named:
            self.assertTrue(run_probe.invisible_named(summary, "live-invisible"),
                            "a character io-guard named still passes")


class ALiveRunDeniedVerdict(unittest.TestCase):
    def summary(self, tools: list, said: str) -> dict:
        return {"claude": "2.1.284", "tools": tools, "results": [{"content": said}], "final": {}}

    def test_a_run_with_no_io_run_call_is_no_verdict(self):
        refused = self.summary([], "The user's CLAUDE.md forbids that command.")
        with mock.patch.object(run_probe, "latest", lambda name: (Path("runs/x"), refused)):
            said = run_probe.verdict("live-run-denied")
        self.assertEqual((said.startswith("no verdict"), "called io.run" in said), (True, True),
                         "a model that never calls io.run says nothing about run.rules, and the line says so")

    def test_the_denied_command_is_one_no_memory_file_forbids(self):
        call = [{"name": run_probe.IO_RUN, "input": {"argv": ["git", "ls-remote", "origin"]}}]
        denied = self.summary(call, "RULE_DENIED: io.run would run git ls-remote origin, which a rule "
                                    "denies.")
        self.assertEqual((run_probe.RUN_RULES["permissions"]["deny"], run_probe.run_denied(denied, "x")),
                         (["Bash(git ls-remote *)"], True),
                         "a read-only command stands in for git push, which the lead's CLAUDE.md forbids")


OUTER = {".gitattributes": b"* text=auto eol=lf\n", ".editorconfig": b"root = true\n[*]\nend_of_line = lf\n",
         ".claude/io-guard.json": b'{"schema": 1, "checks": {"conform.edit": {"enabled": false}}}\n'}


def read_text(path: Path) -> str | None:
    return path.read_bytes().decode("utf-8") if path.is_file() else None


class AWorkFolderIsItsOwnProject(unittest.TestCase):
    def test_a_work_folder_takes_nothing_from_the_repository_around_it(self):
        with TemporaryProject(OUTER, git=True) as outer:
            work = outer / "workbench" / "w"
            run_probe.prepare_work(run_probe.Probe(0, "", ""), work)
            found = (project_root(work), properties(work / "a.h", read_text).get("end_of_line"),
                     Git().attributes(work / "a.txt").get("eol"))
        self.assertEqual(found, (work, None, None),
                         "the work folder is its own project root, and neither the repository's "
                         ".editorconfig nor its .gitattributes reach it")

    def test_a_file_the_probe_gives_is_kept(self):
        with TemporaryProject() as outer:
            own = b"root = true\n[*]\nindent_size = 3\n"
            probe = run_probe.Probe(0, "", "", setup={".editorconfig": own})
            run_probe.prepare_work(probe, outer / "w")
            given = (outer / "w" / ".editorconfig").read_bytes()
        self.assertEqual(given, own, "the probe's own file is never replaced")


if __name__ == "__main__":
    unittest.main()
