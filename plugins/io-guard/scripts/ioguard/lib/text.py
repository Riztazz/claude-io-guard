"""Text shown to the model: the characters it cannot see made visible, a repository's words quoted, and
numbered lines of a file.

The Read tool shows a tab, a trailing space, a CR, a BOM and a private-use glyph as nothing or as a plain
space, which is how an old_string comes to miss. visible writes each as an ASCII marker in brackets, and
snippet numbers the lines as the Read tool does, so the model can match what it sees to what it sent.
invisible_added names the characters of that kind a write brought in, such as the U+FEFF a JSON escape in a
tool call turns into.
"""
import json
import re
from collections import Counter

BOM_CHAR = chr(0xFEFF)
MARKERS = {"\t": "[TAB]", "\r": "[CR]", BOM_CHAR: "[BOM]"}
PRIVATE_RANGES = ((0xE000, 0xF8FF), (0xF0000, 0x10FFFD))
FORMAT_RANGES = ((0xAD, 0xAD), (0x600, 0x605), (0x61C, 0x61C), (0x6DD, 0x6DD), (0x70F, 0x70F), (0x890, 0x891),
                 (0x8E2, 0x8E2), (0x180E, 0x180E), (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064),
                 (0x2066, 0x206F), (0xFEFF, 0xFEFF), (0xFFF9, 0xFFFB), (0x110BD, 0x110BD), (0x110CD, 0x110CD),
                 (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0001, 0xE0001),
                 (0xE0020, 0xE007F))              # Unicode category Cf, 16.0
SPACES = ((0xA0, 0xA0), (0x2028, 0x2029))       # a no-break space, and the line and paragraph separators
INVISIBLE_RANGES = (*FORMAT_RANGES, *SPACES, *PRIVATE_RANGES)
SHOWN = 5               # line numbers a message lists before it gives the rest as a count


def character_class(ranges: tuple[tuple[int, int], ...]) -> str:
    """The inside of a regular expression's [...] for each range of code points, first and last included."""
    return "".join(re.escape(chr(first)) + "-" + re.escape(chr(last)) for first, last in ranges)


INVISIBLE = re.compile(f"[{character_class(INVISIBLE_RANGES)}]")
PRIVATE_USE = re.compile(f"[{character_class(PRIVATE_RANGES)}]")


def invisible_added(before: str, after: str,
                    allowed: frozenset[str] = frozenset()) -> tuple[tuple[int, str], ...]:
    """Each invisible character after holds more of than before does, by its first line in after counted from
    1, as U+XXXX, less the allowed ones. A BOM at the very start of after is the file's, not text."""
    had = Counter(INVISIBLE.findall(before.removeprefix(BOM_CHAR)))
    body = after.removeprefix(BOM_CHAR)
    extra = Counter(INVISIBLE.findall(body)) - had
    found = []
    for char in sorted(extra):
        name = f"U+{ord(char):04X}"
        if name not in allowed:
            found.append((body[:body.find(char)].count("\n") + 1, name))
    return tuple(sorted(found))


def quoted(word: str) -> str:
    """A word from a repository as one JSON string, so a newline, a control character or a quote in it shows
    as an escape and cannot read as io-guard's own text."""
    return json.dumps(word, ensure_ascii=True)


def visible(text: str) -> str:
    """text with each tab, CR, BOM and private-use glyph as a marker, and each trailing space as [SP]."""
    text = "\n".join(trailing_marked(line) for line in text.split("\n"))
    text = PRIVATE_USE.sub(lambda glyph: f"[U+{ord(glyph[0]):04X}]", text)
    return "".join(MARKERS.get(char, char) for char in text)


def trailing_marked(line: str) -> str:
    """line with each space of its trailing spaces and tabs as [SP]. A strip, not a regex, so a long run of
    spaces before text costs one pass."""
    body = line.rstrip(" \t")
    return body + line[len(body):].replace(" ", "[SP]")


def snippet(text: str, first: int, last: int, around: int = 2) -> str:
    """Lines first to last of text, counted from 1, with around more on each side, each numbered as the Read
    tool numbers it and made visible."""
    lines = text.split("\n")
    start, stop = max(1, first - around), min(len(lines), last + around)
    width = len(str(stop))
    return "\n".join(f"{number:>{width}}| {visible(lines[number - 1])}" for number in range(start, stop + 1))


def listed(numbers: tuple[int, ...]) -> str:
    """Line numbers for a message: "line 4", "lines 4 and 9", "lines 1, 2, 3, 4, 5 and 7 more"."""
    shown = [f"{number:,}" for number in numbers[:SHOWN]]
    if not shown:
        return "no line"
    if len(numbers) > SHOWN:
        return f"lines {', '.join(shown)} and {len(numbers) - SHOWN:,} more"
    if len(shown) == 1:
        return f"line {shown[0]}"
    return f"lines {', '.join(shown[:-1])} and {shown[-1]}"


def head(text: str, limit: int) -> str:
    """text cut to limit characters, with the count of what was cut."""
    return text if len(text) <= limit else f"{text[:limit]}\n[{len(text) - limit:,} more characters]"
