"""io-guard's io MCP server, which .mcp.json starts once per Claude Code session: pyrun server.py.

It serves the io tools and the hook tools over stdio until stdin closes. ioguard.mcp.server holds the loop.
"""
import sys

from ioguard.mcp.server import main

if __name__ == "__main__":
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.stdout.write(__doc__)
        sys.exit(0)
    sys.exit(main())
