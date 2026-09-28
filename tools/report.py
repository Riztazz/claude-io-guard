"""python tools/report.py [--data FOLDER ...] [--days 7]

The ioguard report command, run from this checkout. ioguard.cli.report holds the logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "io-guard" / "scripts"))

from ioguard.cli.main import main

sys.exit(main(["report", *sys.argv[1:]]))
