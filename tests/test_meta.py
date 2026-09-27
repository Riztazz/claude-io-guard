"""Checks that keep the suite honest: unique test names, and fixtures that still hold their recorded bytes."""
import ast
import subprocess
import unittest
from collections import defaultdict
from pathlib import Path

from ioguard.checks.registry import default_registry
from ioguard.lib.results import Code
from tests import REPO
from tests.support import fixtures
from tests.support.checks import make_check
from tests.support.meta import checks_without_test_modules, codes_without_tests

TESTS_DIR = REPO / "tests"


def test_sources() -> dict[str, str]:
    """Every test module but this one, which names codes only to check the others."""
    return {path.name: path.read_bytes().decode("utf-8") for path in TESTS_DIR.rglob("test_*.py")
            if path.name != "test_meta.py"}


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


class EveryCodeAndCheckHasATest(unittest.TestCase):
    def test_every_code_is_named_by_a_test(self):
        missing = codes_without_tests([code.value for code in Code], test_sources())
        self.assertEqual(missing, [], "every code in CODES has a test that asserts it was produced")

    def test_every_registered_check_has_a_test_module(self):
        missing = checks_without_test_modules(default_registry().classes.values(), TESTS_DIR)
        self.assertEqual(missing, [], "every shipped check has tests/checks/test_<module>.py")

    def test_the_code_scan_reports_a_code_no_test_names(self):
        sources = {"test_x.py": "self.assertEqual(result.code, Code.GUARD_ERROR)"}
        self.assertEqual(codes_without_tests(["GUARD_ERROR", "NEVER_TESTED"], sources), ["NEVER_TESTED"],
                         "a code no test names makes the meta test fail")

    def test_the_check_scan_reports_a_check_without_a_test_module(self):
        orphan = make_check("demo.orphan", module="ioguard.checks.nothing_tests_this")
        self.assertEqual(checks_without_test_modules([orphan], TESTS_DIR),
                         ["demo.orphan (ioguard.checks.nothing_tests_this)"],
                         "a registered check with no test module makes the meta test fail")


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
