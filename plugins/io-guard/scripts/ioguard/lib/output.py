"""Read a shell command's output: its exit code, the lines that report errors, text a console decoded in the
wrong code page, and the file Claude Code saved a long output to.

A line reports an error only when one of the caller's patterns matches it from its start, so a line that
only quotes an error word, such as "0 errors" or "Errors: 0", reports nothing (OUT-7). The patterns are
policy, so this module takes them as arguments and holds none.
"""
import re
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from ioguard.lib import paths

EXIT = re.compile(r"\AExit code (\d+)")
SAVED = re.compile(r"Output too large \([^)\n]*\)\. Full output saved to: ([^\n]+)")
REPLACEMENT = chr(0xFFFD)
# The characters cp1252 and cp1250 give bytes 0x80 to 0xFF, as ranges of code points
CODE_PAGE_SPANS = ((0x80, 0xFF), (0x102, 0x107), (0x10C, 0x111), (0x118, 0x11B), (0x139, 0x13A),
                   (0x13D, 0x13E), (0x141, 0x144), (0x147, 0x148), (0x150, 0x155), (0x158, 0x165),
                   (0x16E, 0x171), (0x178, 0x17E), (0x192, 0x192), (0x2C6, 0x2C7), (0x2D8, 0x2DD),
                   (0x2013, 0x2014), (0x2018, 0x201E), (0x2020, 0x2022), (0x2026, 0x2026),
                   (0x2030, 0x2030), (0x2039, 0x203A), (0x20AC, 0x20AC), (0x2122, 0x2122))
CODE_PAGE_RUN = re.compile("[" + "".join(f"{chr(low)}-{chr(high)}" for low, high in CODE_PAGE_SPANS)
                           + "]{2,}")


@dataclass(frozen=True)
class ErrorLine:
    number: int                  # counted from 1
    kind: str                    # the name of the pattern group that matched, such as "compiler"
    text: str


@dataclass(frozen=True)
class Mojibake:
    replaced: int                # U+FFFD characters, each standing for bytes that were not UTF-8
    garbled: int                 # runs that read as UTF-8 once encoded back into a code page
    example: str | None          # the first such run, and what it meant
    meant: str | None


def exit_code(error: str) -> int | None:
    """The exit code a failed Bash or PowerShell call reports on its first line, or None."""
    found = EXIT.match(error)
    return None if found is None else int(found[1])


def saved_path(response: Mapping[str, Any]) -> str | None:
    """The file Claude Code saved a long output to: persistedOutputPath, or the path its notice in stdout
    names. None when the output was shown whole."""
    path = response.get("persistedOutputPath")
    if isinstance(path, str) and path:
        return path
    found = SAVED.search(str(response.get("stdout") or "")[:1_000])
    return None if found is None else found[1].strip()


def in_tool_results(path: str, claude: Path, session_id: str) -> bool:
    """Whether path, after .. and links, is a file in the folder where Claude Code saves this session's long
    outputs: <claude>/projects/<project>/<session>/tool-results, or a tool-results folder below it. The
    notice's text is the command's own output, so it can name any file."""
    try:
        parts = PurePath(paths.resolved(Path(path))).relative_to(paths.resolved(claude / "projects")).parts
    except (ValueError, OSError):
        return False
    return len(parts) >= 4 and parts[1].casefold() == session_id.casefold() and "tool-results" in parts[2:-1]


def compiled(value: Mapping[str, Sequence[str]]) -> dict[str, re.Pattern]:
    """One multiline pattern per group of error patterns, each matching any pattern of its group."""
    return {name: re.compile("|".join(f"(?:{item})" for item in listed), re.M)
            for name, listed in value.items() if listed}


def error_lines(text: str, patterns: Mapping[str, re.Pattern]) -> tuple[ErrorLine, ...]:
    """Each line of text a pattern matches from its start, in order, with the name of its group. A line two
    groups match counts once, for the group named first. Each pattern needs re.MULTILINE."""
    kinds: dict[int, str] = {}
    for kind, pattern in patterns.items():
        for match in pattern.finditer(text):
            kinds.setdefault(match.start(), kind)
    if not kinds:
        return ()
    starts = [0, *(match.end() for match in re.finditer("\n", text))]
    found = []
    for start in sorted(kinds):
        number = bisect_right(starts, start)
        line = text[starts[number - 1]:starts[number] - 1 if number < len(starts) else len(text)]
        found.append(ErrorLine(number, kinds[start], line.rstrip("\r")))
    return tuple(found)


def mojibake(text: str, code_pages: Sequence[str]) -> Mojibake:
    """The U+FFFD characters in text, and the runs of code page characters that decode as UTF-8 once encoded
    in one of code_pages, which is how a console shows UTF-8 it read in its own code page."""
    garbled, example, meant = 0, None, None
    for run in CODE_PAGE_RUN.finditer(text):
        decoded = decode_back(run[0], code_pages)
        if decoded is not None:
            garbled += 1
            if example is None:
                example, meant = run[0], decoded
    return Mojibake(text.count(REPLACEMENT), garbled, example, meant)


def decode_back(run: str, code_pages: Sequence[str]) -> str | None:
    """What run meant, when its code page bytes are UTF-8 holding a character beyond ASCII, else None."""
    for code_page in code_pages:
        try:
            decoded = run.encode(code_page).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if decoded != run and any(ord(char) > 127 for char in decoded):
            return decoded
    return None


def excerpt(text: str, head: int, tail: int, marked: Sequence[ErrorLine], width: int) -> str:
    """The first head lines of text, the marked lines between them, and the last tail lines, each numbered
    from 1 as the Read tool numbers them and cut to width characters. A bracketed line says what each gap left
    out."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    count = len(lines)
    shown = sorted({*range(1, min(head, count) + 1), *range(max(1, count - tail + 1), count + 1),
                    *(line.number for line in marked if line.number <= count)})
    numbers = len(f"{count:,}")
    out, last = [], 0
    for number in shown:
        if number > last + 1:
            left = number - last - 1
            out.append(f"[{left:,} line{'s' if left > 1 else ''} left out, {last + 1:,} to {number - 1:,}]")
        line = lines[number - 1].rstrip("\r")
        cut = f" [{len(line) - width:,} more characters]" if len(line) > width else ""
        out.append(f"{number:>{numbers},}| {line[:width]}{cut}")
        last = number
    return "\n".join(out)
