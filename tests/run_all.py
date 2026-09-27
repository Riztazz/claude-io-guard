"""Run the suite the way python -m unittest discover -s tests -t . does, and fail when it finds no tests.

    python tests/run_all.py [<start folder>]

CI runs this. A discovery step that finds nothing reports success, so zero tests counts as a failure here.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(argv: list[str]) -> int:
    start = Path(argv[0]).resolve() if argv else REPO / "tests"
    suite = unittest.defaultTestLoader.discover(str(start), top_level_dir=str(REPO))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.testsRun == 0:
        print(f"No tests ran from {start}. Discovery found nothing, so this run proves nothing.",
              file=sys.stderr)
        return 1
    print(f"{result.testsRun} tests ran from {start}.", file=sys.stderr)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
