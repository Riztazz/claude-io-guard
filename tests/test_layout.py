"""The package keeps its layers: lib imports only the standard library and lib, and each policy package
imports lib and never another policy package."""
import ast
import sys
import unittest
from pathlib import Path

from tests import PLUGIN_SCRIPTS

PACKAGE = PLUGIN_SCRIPTS / "ioguard"
POLICY = ("checks", "hooks", "mcp", "cli")
BRIDGES = {("hooks", "bridge"), ("mcp", "tools_hook")}   # the two modules that call hooks.entry


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


class PackageLayers(unittest.TestCase):
    def test_lib_imports_only_the_standard_library_and_lib(self):
        for path in modules("lib"):
            for name in imports_of(path):
                with self.subTest(module=path.name, imports=name):
                    self.assertTrue(standard(name) or name == "ioguard" or name.startswith("ioguard.lib"),
                                    "a lib module imports only the standard library and other lib modules")

    def test_a_policy_package_imports_lib_and_never_another_policy_package(self):
        for subpackage in POLICY:
            for path in modules(subpackage):
                for name in imports_of(path):
                    parts = name.split(".")
                    other = len(parts) > 1 and parts[0] == "ioguard" and parts[1] in POLICY \
                        and parts[1] != subpackage
                    allowed = (subpackage, path.stem) in BRIDGES and name == "ioguard.hooks.entry"
                    with self.subTest(module=f"{subpackage}/{path.name}", imports=name):
                        self.assertFalse(other and not allowed,
                                         "checks, hooks, mcp and cli import lib and never each other")

    def test_the_scan_sees_the_packages_it_guards(self):
        self.assertTrue(modules("lib") and modules("checks"),
                        "the layer test reads real modules, so it cannot pass on an empty tree")
        self.assertLessEqual({"ioguard.lib.config", "ioguard.lib.git"},
                             imports_of(PACKAGE / "lib" / "context.py"),
                             "the import scan finds the imports a module really has")


if __name__ == "__main__":
    unittest.main()
