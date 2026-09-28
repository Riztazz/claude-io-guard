"""Checks that keep the suite honest: unique test names, and fixtures that still hold their recorded bytes."""
import ast
import os
import subprocess
import sys
import tempfile
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
    return {path.relative_to(TESTS_DIR).as_posix(): path.read_bytes().decode("utf-8")
            for path in TESTS_DIR.rglob("test_*.py") if path.name != "test_meta.py"}


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


class PythonLinesStopAt110(unittest.TestCase):
    def test_no_python_line_in_the_repository_is_longer_than_110_characters(self):
        long = [f"{path.relative_to(REPO).as_posix()}:{number}"
                for folder in ("plugins", "tests", "tools") for path in sorted((REPO / folder).rglob("*.py"))
                if "__pycache__" not in path.parts
                for number, line in enumerate(path.read_bytes().decode("utf-8").splitlines(), 1)
                if len(line) > 110]
        self.assertEqual(long, [], "D17: code and comments stop at 110 characters")


def scripts() -> list[Path]:
    """Every file under tools/ and the plugin's scripts/ that runs as a program: it calls main or checks
    __main__. The ioguard package is modules, not scripts."""
    found = [*(REPO / "tools").rglob("*.py"), *(REPO / "plugins" / "io-guard" / "scripts").glob("*.py")]
    marks = (b'__name__ == "__main__"', b"sys.exit(main(")
    return sorted(path for path in found if "__pycache__" not in path.parts
                  and any(mark in path.read_bytes() for mark in marks))


def stats() -> dict[str, tuple[int, int]]:
    """Each file git tracks or sees in the checkout, ignored ones too, with its modification time and size."""
    listed = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z", "--cached", "--others"],
                            cwd=REPO, capture_output=True, check=True, timeout=60).stdout
    found = {}
    for name in {name.decode("utf-8") for name in listed.split(b"\0") if name}:
        try:
            stat = (REPO / name).stat()
        except OSError:
            continue
        found[name] = (stat.st_mtime_ns, stat.st_size)
    return found


class EveryScriptAnswersHelp(unittest.TestCase):
    def test_every_script_prints_its_usage_for_help_and_does_nothing_else(self):
        found = scripts()
        self.assertGreaterEqual(len(found), 12,
                                "the scan finds the tools, the probes and the plugin's scripts")
        with tempfile.TemporaryDirectory(prefix="ioguard-help-") as home:
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "IOGUARD_HOME": home}
            before = stats()
            for path in found:
                with self.subTest(script=path.relative_to(REPO).as_posix()):
                    done = subprocess.run([sys.executable, str(path), "--help"], cwd=REPO, env=env,
                                          stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
                    doc = ast.get_docstring(ast.parse(path.read_bytes())) or ""
                    said = done.stdout.decode("utf-8", "replace")
                    self.assertEqual(done.returncode, 0, f"--help exits 0: {done.stderr[-400:]!r}")
                    self.assertTrue("usage:" in said or (doc and doc.splitlines()[0] in said),
                                    f"--help prints argparse's usage or the docstring: {said[:200]!r}")
            changed = sorted(name for name, stat in stats().items() if before.get(name) != stat)
        self.assertEqual(changed, [], "--help writes no file in the checkout")


if __name__ == "__main__":
    unittest.main()
