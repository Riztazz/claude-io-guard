"""The scans test_meta runs over the suite: codes no test names, and checks no test module covers."""
import re
from collections.abc import Iterable, Mapping
from pathlib import Path


def codes_without_tests(code_names: Iterable[str], test_sources: Mapping[str, str]) -> list[str]:
    """Each code that no test module names as Code.<NAME>, the way a test asserts it was produced."""
    named = {match for source in test_sources.values()
             for match in re.findall(r"\bCode\.([A-Z_]+)\b", source)}
    return [name for name in code_names if name not in named]


def checks_without_test_modules(check_classes: Iterable[type], tests_dir: Path) -> list[str]:
    """Each check whose module, ioguard.checks.<name>, has no tests/checks/test_<name>.py."""
    missing = []
    for check_class in check_classes:
        module = check_class.__module__.rsplit(".", 1)[-1]
        if not (tests_dir / "checks" / f"test_{module}.py").is_file():
            missing.append(f"{check_class.meta.id} ({check_class.__module__})")
    return missing
