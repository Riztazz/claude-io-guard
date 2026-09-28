"""io-guard's test suite. From the repository root: python -m unittest discover -s tests -t .

Importing the package puts plugins/io-guard/scripts on the path, so a test imports ioguard as the hooks do.
Under a test runner it also points IOGUARD_HOME at a temporary folder, so no test, and no process a test
starts, reads or writes the user's own io-guard folder. A hook or server with the test checks injected imports
this package too, with no test runner loaded, and keeps the IOGUARD_HOME it was started with.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN_SCRIPTS = REPO / "plugins" / "io-guard" / "scripts"
if str(PLUGIN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS))

if "unittest" in sys.modules:
    TEST_HOME = Path(tempfile.mkdtemp(prefix="ioguard-tests-home-"))
    os.environ["IOGUARD_HOME"] = str(TEST_HOME)
    atexit.register(shutil.rmtree, TEST_HOME, True)
