"""python tools/ioguard.py COMMAND ...

The ioguard command line, run from this checkout: check, profile, and every other command in ioguard.cli.main.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "io-guard" / "scripts"))

from ioguard.cli.main import main

sys.exit(main(sys.argv[1:]))
