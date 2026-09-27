"""Text shown to the model: the characters it cannot see made visible, and numbered lines of a file.

The Read tool shows a tab, a trailing space, a CR, a BOM and a private-use glyph as nothing or as a plain
space, which is how an old_string comes to miss. visible writes each as an ASCII marker in brackets, and
snippet numbers the lines as the Read tool does, so the model can match what it sees to what it sent.
"""
import re

PRIVATE_USE = re.compile(f"[{chr(0xE000)}-{chr(0xF8FF)}{chr(0xF0000)}-{chr(0x10FFFD)}]")
TRAILING = re.compile(r"[ \t]+$", re.M)
MARKERS = {"\t": "[TAB]", "\r": "[CR]", chr(0xFEFF): "[BOM]"}


def visible(text: str) -> str:
    """text with each tab, CR, BOM and private-use glyph as a marker, and each trailing space as [SP]."""
    text = TRAILING.sub(lambda run: run[0].replace(" ", "[SP]"), text)
    text = PRIVATE_USE.sub(lambda glyph: f"[U+{ord(glyph[0]):04X}]", text)
    return "".join(MARKERS.get(char, char) for char in text)


def snippet(text: str, first: int, last: int, around: int = 2) -> str:
    """Lines first to last of text, counted from 1, with around more on each side, each numbered as the Read
    tool numbers it and made visible."""
    lines = text.split("\n")
    start, stop = max(1, first - around), min(len(lines), last + around)
    width = len(str(stop))
    return "\n".join(f"{number:>{width}}| {visible(lines[number - 1])}" for number in range(start, stop + 1))


def head(text: str, limit: int) -> str:
    """text cut to limit characters, with the count of what was cut."""
    return text if len(text) <= limit else f"{text[:limit]}\n[{len(text) - limit:,} more characters]"
