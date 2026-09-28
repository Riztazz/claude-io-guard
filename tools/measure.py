"""python tools/measure.py NAME=FOLDER [NAME=FOLDER ...] [--since YYYY-MM-DD] [--data FOLDER ...]

The ioguard measure command, run from this checkout. ioguard.cli.measure holds the logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "io-guard" / "scripts"))

from ioguard.cli.main import main

sys.exit(main(["measure", *sys.argv[1:]]))
