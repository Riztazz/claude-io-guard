"""The package keeps its layers: lib imports only the standard library and lib, a check imports lib and
checks.base, and hooks, mcp and cli import lib and the pipeline and registry and never each other."""
import ast
import sys
import unittest
from pathlib import Path

from tests import PLUGIN_SCRIPTS

PACKAGE = PLUGIN_SCRIPTS / "ioguard"
SURFACES = ("hooks", "mcp", "cli")                  # the ways in, which all run the checks
BRIDGE = (("mcp", "tools_hook"), "ioguard.hooks.bridge")   # the one import between two surfaces
FRAMEWORK = {"base", "pipeline", "registry"}         # the checks modules that hold no check
RUNNERS = {"ioguard.checks.pipeline", "ioguard.checks.registry"}   # what a surface takes from checks
SHORT = 40                                           # the most lines a function of the split modules has


def imports_of(path: Path) -> set[str]:
    """Every module name a file imports, absolute or resolved from a relative import."""
    tree = ast.parse(path.read_bytes(), filename=str(path))
    package = ".".join(path.relative_to(PLUGIN_SCRIPTS).with_suffix("").parts[:-1])
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parent = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                base = f"{parent}.{base}" if base else parent
            found.add(base)
    return found


def modules(subpackage: str) -> list[Path]:
    return sorted((PACKAGE / subpackage).glob("*.py"))


def standard(name: str) -> bool:
    return name.split(".")[0] in sys.stdlib_module_names


def package_of(name: str) -> str | None:
    """The ioguard subpackage an import names, such as checks for ioguard.checks.pipeline, or None."""
    parts = name.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "ioguard" else None


class PackageLayers(unittest.TestCase):
    def test_lib_imports_only_the_standard_library_and_lib(self):
        for path in modules("lib"):
            for name in imports_of(path):
                with self.subTest(module=path.name, imports=name):
                    self.assertTrue(standard(name) or name == "ioguard" or name.startswith("ioguard.lib"),
                                    "a lib module imports only the standard library and other lib modules")

    def test_checks_imports_lib_and_never_a_surface(self):
        for path in modules("checks"):
            for name in imports_of(path):
                with self.subTest(module=path.name, imports=name):
                    self.assertFalse(package_of(name) in SURFACES,
                                     "checks runs the same under every surface, so it never imports one")

    def test_a_surface_imports_lib_and_checks_and_never_another_surface(self):
        for subpackage in SURFACES:
            for path in modules(subpackage):
                for name in imports_of(path):
                    other = package_of(name) in SURFACES and package_of(name) != subpackage
                    allowed = ((subpackage, path.stem), name) == BRIDGE
                    with self.subTest(module=f"{subpackage}/{path.name}", imports=name):
                        self.assertFalse(other and not allowed,
                                         "hooks, mcp and cli import lib and checks and never each other")

    def test_a_check_imports_no_other_check(self):
        for path in modules("checks"):
            if path.stem in FRAMEWORK:
                continue
            for name in imports_of(path):
                with self.subTest(module=path.name, imports=name):
                    self.assertFalse(name.startswith("ioguard.checks") and name != "ioguard.checks.base",
                                     "a check takes its mechanism from lib, so no check is another's library")

    def test_a_surface_takes_only_the_pipeline_and_the_registry_from_checks(self):
        for subpackage in SURFACES:
            for path in modules(subpackage):
                for name in imports_of(path):
                    with self.subTest(module=f"{subpackage}/{path.name}", imports=name):
                        self.assertFalse(name.startswith("ioguard.checks") and name not in RUNNERS,
                                         "a way in runs the checks and takes its mechanism from lib")

    def test_the_split_functions_stay_short(self):
        for module in ("checks/touched.py", "checks/shell_writes.py", "checks/command_results.py",
                       "lib/writes.py"):
            tree = ast.parse((PACKAGE / module).read_bytes())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    with self.subTest(module=module, function=node.name):
                        self.assertLessEqual(node.end_lineno - node.lineno + 1, SHORT,
                                             "a function that does several jobs is split into one per job")

    def test_the_scan_sees_the_packages_it_guards(self):
        self.assertTrue(modules("lib") and modules("checks") and modules("hooks"),
                        "the layer test reads real modules, so it cannot pass on an empty tree")
        self.assertIn("ioguard.checks.pipeline", imports_of(PACKAGE / "hooks" / "entry.py"),
                      "the surface scan sees hooks.entry run the pipeline")
        self.assertLessEqual({"ioguard.lib.config", "ioguard.lib.git"},
                             imports_of(PACKAGE / "lib" / "context.py"),
                             "the import scan finds the imports a module really has")


if __name__ == "__main__":
    unittest.main()
