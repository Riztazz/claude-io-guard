"""io-guard's optional git pre-commit hook: python <plugin folder>/scripts/precommit.py, run by git before
each commit.

It compares each staged text file with its last commit, and stops the commit when the staged bytes change
the file's line endings, BOM, encoding or indent style, or add control bytes, U+FFFD, or non-ASCII in a file
the project keeps ASCII. ioguard.cli.precommit holds the logic. git commit --no-verify skips it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ioguard.cli.main import main

sys.exit(main(["precommit", *sys.argv[1:]]))
