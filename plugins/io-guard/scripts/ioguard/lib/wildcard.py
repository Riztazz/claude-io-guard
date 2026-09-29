"""Matching a pattern where * stands for any text, newlines included, against a whole string.

A regex of .* joins backtracks at every star, so a pattern of eight stars costs the eighth power of the text's
length when it almost matches. This walk keeps one backtrack point, the last star, which costs at most the
text's length times the pattern's.
"""


def match(pattern: str, text: str, fold: bool = False) -> bool:
    """Whether text is pattern with each * standing for any text. fold compares without case."""
    if fold:
        pattern, text = pattern.casefold(), text.casefold()
    at, star, resume, mark = 0, -1, 0, 0
    while resume < len(text):
        if at < len(pattern) and pattern[at] == "*":
            star, mark, at = at, resume, at + 1
        elif at < len(pattern) and pattern[at] == text[resume]:
            at, resume = at + 1, resume + 1
        elif star >= 0:
            mark += 1
            at, resume = star + 1, mark
        else:
            return False
    return all(char == "*" for char in pattern[at:])
