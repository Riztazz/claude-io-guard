"""The platform io-guard runs on, detected once. Every platform difference reads it, never sys.platform.

lib.probing measures the rest of the machine at session start: the shells, their versions and the console.
"""
import sys
from dataclasses import dataclass
from functools import cache

WINDOWS = "win32"
MACOS = "darwin"
EVERY_PLATFORM = frozenset({WINDOWS, MACOS})     # the platforms io-guard is built and tested for


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
