"""python tools/corpus.py NAME=FOLDER [NAME=FOLDER ...] [--out corpus]

The ioguard corpus command, run from this checkout. ioguard.cli.corpus holds the logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "io-guard" / "scripts"))

from ioguard.cli.main import main

sys.exit(main(["corpus", *sys.argv[1:]]))
