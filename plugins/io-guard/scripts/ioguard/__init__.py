"""io-guard checks what an agent sends to the file and shell tools, fixes what it safely can, and
refuses the rest.

lib holds the mechanism and imports nothing else. checks holds the pipeline and the checks, and imports lib.
hooks, mcp and cli import lib and checks, and never each other, except that mcp calls hooks.bridge. A log
record reaches only the debug log, which telemetry.debug turns on, so stdout and stderr stay the protocol's.
"""
import logging

logging.getLogger("ioguard").addHandler(logging.NullHandler())

PLUGIN_VERSION = "0.1"
CONFIG_SCHEMA = 1
CHECK_API = 1
TELEMETRY_SCHEMA = 1
