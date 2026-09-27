"""The platform io-guard runs on, detected once. Every platform difference reads it, never sys.platform.

Task 10 adds the session probe: the shells, their versions and the transport budget.
"""
import sys
from dataclasses import dataclass
from functools import cache

WINDOWS = "win32"
MACOS = "darwin"


@dataclass(frozen=True)
class Platform:
    os: str                      # sys.platform: "win32", "darwin", or another value on an untested system
    case_insensitive: bool       # the default file system ignores case in names

    @property
    def windows(self) -> bool:
        return self.os == WINDOWS

    @property
    def macos(self) -> bool:
        return self.os == MACOS


@cache
def detect() -> Platform:
    return Platform(os=sys.platform, case_insensitive=sys.platform in (WINDOWS, MACOS))
