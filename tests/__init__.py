"""io-guard's test suite. From the repository root: python -m unittest discover -s tests -t .

Importing the package puts plugins/io-guard/scripts on the path, so a test imports ioguard as the hooks do.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS = REPO / "plugins" / "io-guard" / "scripts"
if str(PLUGIN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS))
