"""The probe runner's verdicts tell a model that skipped the probe's step from io-guard failing it."""
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
