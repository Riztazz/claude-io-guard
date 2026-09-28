"""python tools/skill.py [--check]

Writes the tool and code tables into the io-guard skill page, or with --check exits 1 when they are out of
date. ioguard.mcp.skill holds the logic, beside the tool registry it reads.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "io-guard" / "scripts"))

from ioguard.mcp.skill import main

sys.exit(main(sys.argv[1:]))
