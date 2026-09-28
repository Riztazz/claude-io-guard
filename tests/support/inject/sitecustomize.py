"""Adds the test checks IOGUARD_TEST_CHECKS names, comma-separated, to io-guard in a Python a test starts.

Python imports sitecustomize at startup from any folder on PYTHONPATH. A test that puts this folder there runs
hook.py or ioguard_mcp.py as shipped, with its checks installed by tests/support/injected.py. When the file
IOGUARD_TEST_DEAD names exists, ioguard_mcp.py exits at once, as a server that cannot start again does.
"""
import os
import sys
from pathlib import Path

DEAD = os.environ.get("IOGUARD_TEST_DEAD", "")
if DEAD and Path(DEAD).is_file() and sys.argv and sys.argv[0].endswith("ioguard_mcp.py"):
    os._exit(3)

NAMES = os.environ.get("IOGUARD_TEST_CHECKS", "")
if NAMES:
    REPO = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(REPO), str(REPO / "plugins" / "io-guard" / "scripts")]
    from tests.support import injected
    injected.install(name for name in NAMES.split(",") if name)
