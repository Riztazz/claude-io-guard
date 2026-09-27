"""python tools/replay.py [--corpus corpus] [--project NAME ...] [--out FILE]

The ioguard replay command, run from this checkout. ioguard.cli.replay holds the logic.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "io-guard" / "scripts"))

from ioguard.cli.main import main

sys.exit(main(["replay", *sys.argv[1:]]))
