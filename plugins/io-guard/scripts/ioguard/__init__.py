"""io-guard checks what an agent sends to the file and shell tools, fixes what it safely can, and
refuses the rest.

lib holds the mechanism. checks, hooks, mcp and cli hold the policy, and import lib and never each other.
"""

PLUGIN_VERSION = "0.1"
CONFIG_SCHEMA = 1
CHECK_API = 1
TELEMETRY_SCHEMA = 1
