"""Checks that keep the suite honest: unique test names, and fixtures that still hold their recorded bytes."""
import ast
import subprocess
import unittest
from collections import defaultdict
from pathlib import Path

from tests import REPO
from tests.support import fixtures

TESTS_DIR = REPO / "tests"


def test_methods() -> dict[str, list[str]]:
    """Every test method in the suite, as {name: ["file:line", ...]}."""
    found = defaultdict(list)
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        tree = ast.parse(path.read_bytes(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for member in node.body:
                    if isinstance(member, ast.FunctionDef) and member.name.startswith("test"):
                        found[member.name].append(f"{path.relative_to(REPO).as_posix()}:{member.lineno}")
    return found


class TestNamesAreUniqueAcrossTheSuite(unittest.TestCase):
    def test_no_test_method_name_appears_twice(self):
        repeated = {name: places for name, places in test_methods().items() if len(places) > 1}
        self.assertEqual(repeated, {}, "a test name used twice replaces or hides the other test, and the run "
                                       "stays green one test short")

    def test_the_scan_finds_the_tests_in_this_file(self):
        self.assertIn("test_no_test_method_name_appears_twice", test_methods(),
                      "the duplicate scan reads every test module, this one included")


class FixturesKeepTheirRecordedBytes(unittest.TestCase):
    def test_every_fixture_file_is_in_the_manifest(self):
        unlisted = [fixtures.manifest_name(path) for path in fixtures.fixture_files()
                    if fixtures.manifest_name(path) not in fixtures.read_manifest()]
        self.assertEqual(unlisted, [], "every fixture has a hash in MANIFEST.sha256, so a changed byte shows")

    def test_every_manifest_entry_names_an_existing_fixture(self):
        missing = [name for name in fixtures.read_manifest() if not (fixtures.FIXTURES_DIR / name).is_file()]
        self.assertEqual(missing, [], "MANIFEST.sha256 lists only fixtures that exist")

    def test_every_fixture_has_the_hash_the_manifest_records(self):
        manifest = fixtures.read_manifest()
        for path in fixtures.fixture_files():
            name = fixtures.manifest_name(path)
            with self.subTest(fixture=name):
                self.assertEqual(fixtures.digest(path), manifest.get(name),
                                 f"{name} holds other bytes than the manifest records, so git or an editor "
                                 f"converted it")

    def test_every_generated_fixture_holds_its_definition(self):
        for name, data in fixtures.GENERATED.items():
            with self.subTest(fixture=name):
                self.assertEqual((fixtures.FIXTURES_DIR / name).read_bytes(), data,
                                 f"{name} matches its bytes in tests/support/fixtures.py")

    def test_git_treats_every_fixture_as_not_text(self):
        names = [path.relative_to(REPO).as_posix() for path in fixtures.fixture_files()]
        done = subprocess.run(["git", "-c", "core.quotepath=false", "check-attr", "text", "--", *names],
                              cwd=REPO, capture_output=True, timeout=60, check=True)
        lines = done.stdout.decode("utf-8").splitlines()
        text = [line for line in lines if not line.endswith(": text: unset")]
        self.assertEqual(len(lines), len(names), "git check-attr answered once per fixture")
        self.assertEqual(text, [],
                         ".gitattributes marks tests/fixtures -text, so git never converts a fixture")


if __name__ == "__main__":
    unittest.main()
