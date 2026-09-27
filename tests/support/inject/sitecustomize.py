"""Adds the test checks IOGUARD_TEST_CHECKS names, comma-separated, to io-guard in a Python a test starts.

Python imports sitecustomize at startup from any folder on PYTHONPATH. A test that puts this folder there runs
hook.py or server.py as shipped, with its checks installed by tests/support/injected.py.
"""
import os
import sys
from pathlib import Path

NAMES = os.environ.get("IOGUARD_TEST_CHECKS", "")
if NAMES:
    REPO = Path(__file__).resolve().parents[3]
    sys.path[:0] = [str(REPO), str(REPO / "plugins" / "io-guard" / "scripts")]
    from tests.support import injected
    injected.install(name for name in NAMES.split(",") if name)
