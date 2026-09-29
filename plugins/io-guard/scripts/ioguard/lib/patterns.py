"""Whether a regular expression from a file io-guard did not write is safe to run on every line of output.

Python's re has no timeout, and a group that repeats inside another repetition, such as (a+)+, can backtrack
for seconds on one line that almost matches. A cloned repository's project file can set such a pattern, and
io-guard would run it in the io server on each command's output. So a pattern from a project file is refused
when it does not compile, when it is long, when a quantified group holds a quantifier or a | choice of its
own, or when it holds more than two open repeats such as .* or \\d+, whose cost on one line grows as the
line's length to that power. The rule also refuses some patterns that are safe, such as (?:,\\d+)*, which the
user's own config.json may still set.
"""
import re

LONGEST = 200
QUANTIFIERS = "*+{"
OPEN_REPEATS = 2


def problem(pattern: str) -> str | None:
    """Why pattern is not safe to run from a project file, as one sentence, or None."""
    try:
        re.compile(pattern)
    except re.error as error:
        return f"The pattern {pattern!r} does not compile: {error}."
    if len(pattern) > LONGEST:
        return f"The pattern that starts {pattern[:40]!r} is longer than {LONGEST} characters."
    if nested(pattern):
        return (f"The pattern {pattern!r} repeats a group that repeats or chooses inside, which can take "
                f"seconds on one line. Set it in your own config.json if it must stay.")
    if open_repeats(pattern) > OPEN_REPEATS:
        return (f"The pattern {pattern!r} holds more than {OPEN_REPEATS} open repeats such as * or +, which "
                f"can take seconds on one line. Set it in your own config.json if it must stay.")
    return None


def nested(pattern: str) -> bool:
    """A group followed by *, + or a {} count past one, whose own text holds *, + or {, or a choice with |,
    whose branches can match the same text in more than one way."""
    stack: list[bool] = [False]
    choices: list[bool] = [False]
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            index = class_end(pattern, index)
            continue
        if char == "(":
            stack.append(False)
            choices.append(False)
        elif char == "|":
            choices[-1] = True
        elif char == ")" and len(stack) > 1:
            inner, choice = stack.pop(), choices.pop()
            repeated = repeats(pattern, index + 1)
            if (inner or choice) and repeated:
                return True
            stack[-1] = stack[-1] or inner or repeated
        elif char in QUANTIFIERS and repeats(pattern, index):
            stack[-1] = True
        index += 1
    return False


def open_repeats(pattern: str) -> int:
    """How many *, + or {n,} the pattern holds outside character classes and escapes. Each one past the
    second multiplies what one line that almost matches can cost."""
    count, index = 0, 0
    while index < len(pattern):
        char = pattern[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            index = class_end(pattern, index)
            continue
        if char in "*+" or (char == "{" and re.match(r"\{\d*,\}", pattern[index:])):
            count += 1
        index += 1
    return count


def repeats(pattern: str, index: int) -> bool:
    """The text at index is *, + or a {} count that allows more than one."""
    if index >= len(pattern):
        return False
    if pattern[index] in "*+":
        return True
    count = re.match(r"\{(\d*)(,?)(\d*)\}", pattern[index:])
    if count is None:
        return False
    low, comma, high = count.groups()
    return bool(comma) and (not high or int(high) > 1) or (not comma and low != "" and int(low) > 1)


def class_end(pattern: str, index: int) -> int:
    """The index after the character class that starts at index."""
    index += 1
    if index < len(pattern) and pattern[index] == "^":
        index += 1
    if index < len(pattern) and pattern[index] == "]":
        index += 1
    while index < len(pattern) and pattern[index] != "]":
        index += 2 if pattern[index] == "\\" else 1
    return index + 1


def list_problem(value: list) -> str | None:
    """What is wrong in a list of regular expressions: an item that is not a string, or does not compile."""
    for item in value:
        if not isinstance(item, str):
            return "Each item must be a regular expression, as a string."
        try:
            re.compile(item)
        except re.error as error:
            return f"The pattern {item!r} does not compile: {error}."
    return None


def leaves(value: object) -> list[str]:
    """Every string in a config value: the value itself, a list's items, or a mapping's values, nested."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in leaves(item)]
    if isinstance(value, list):
        return [text for item in value for text in leaves(item)]
    return []
