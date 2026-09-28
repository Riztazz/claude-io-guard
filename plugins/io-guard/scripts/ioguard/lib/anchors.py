"""Where an Edit's old_string sits in a file, where it nearly sits, the shortest text naming one place, and
where an Edit joins the text after its match.

Everything works on the file as the Edit tool reads it: text, every line ending read as LF, no BOM. A miss is
usually whitespace: a tab where the call has spaces, a trailing space, an indent one level off. So closest
first looks for old_string with every space and tab ignored on both sides, through a plain substring search,
and a match there is exact enough to correct the call. Otherwise it scores windows of the file's lines
against old_string's lines and returns the best few.
"""
import bisect
import difflib
import re
from dataclasses import dataclass

SPACE_RUN = re.compile(r"[ \t]+")
WORD_RUN = re.compile(r"[^ \t]+")
FUZZY_FLOOR = 0.5          # a window scoring below this is not offered as a near miss
FUZZY_LINES = 20_000       # past this many lines the fuzzy search is skipped, as too slow for a hook
FUZZY_STARTS = 400         # the most windows scored, from the lines most like old_string's longest line


@dataclass(frozen=True)
class Match:
    start: int                       # offset in the text
    end: int
    first_line: int                  # counted from 1
    last_line: int


@dataclass(frozen=True)
class Candidate:
    match: Match
    text: str                        # the file's own text for the region
    score: float                     # 1.0 when only whitespace differs
    exact: bool                      # the region equals old_string once whitespace is ignored


def edit_view(text: str) -> str:
    """text as the Edit tool reads it, with every CRLF and every lone CR as LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def match_at(text: str, start: int, end: int) -> Match:
    return Match(start, end, line_of(text, start), line_of(text, max(start, end - 1)))


def find(text: str, anchor: str) -> tuple[Match, ...]:
    """Every place anchor appears, left to right and not overlapping, as the Edit tool counts them."""
    found, at = [], text.find(anchor) if anchor else -1
    while at >= 0:
        found.append(match_at(text, at, at + len(anchor)))
        at = text.find(anchor, at + len(anchor))
    return tuple(found)


@dataclass(frozen=True)
class Joined:
    """A line an Edit leaves with new_string's last character against the text after the match."""
    line: int                        # the match's last line, counted from 1 before the Edit
    after: str                       # that line as the Edit leaves it
    next: str                        # the character the dropped spaces stood before


def joins(text: str, old: str, new: str, every: bool) -> tuple[Joined, ...]:
    """Each place where replacing old with new drops the spaces or tabs old ends with, while the line goes
    on after the match. Only the one match counts unless every, as the Edit tool refuses a repeated one. None
    when new is empty, keeps some whitespace at its end, or old is only whitespace."""
    trimmed = old.rstrip(" \t")
    if not new or trimmed in ("", old) or new != new.rstrip(" \t"):
        return ()
    matches = find(text, old)
    if not every and len(matches) != 1:
        return ()
    found = []
    for match in matches:
        following = text[match.end:match.end + 1]
        if following in ("", " ", "\t", "\n"):
            continue
        start, stop = text.rfind("\n", 0, match.start) + 1, text.find("\n", match.end)
        head = (text[start:match.start] + new).rsplit("\n", 1)[-1]
        found.append(Joined(match.last_line, head + text[match.end:None if stop < 0 else stop], following))
    return tuple(found)


@dataclass(frozen=True)
class Squeezed:
    """Text with its spaces and tabs removed, and where each kept run of characters starts in the text."""
    text: str
    kept_starts: list[int]           # where each run starts in the squeezed text
    starts: list[int]                # where the same run starts in the original text

    @classmethod
    def of(cls, text: str) -> "Squeezed":
        runs = list(WORD_RUN.finditer(text))
        kept_starts, total = [], 0
        for run in runs:
            kept_starts.append(total)
            total += len(run[0])
        return cls("".join(run[0] for run in runs), kept_starts, [run.start() for run in runs])

    def original(self, index: int) -> int:
        """The offset in the original text of the squeezed character at index."""
        run = bisect.bisect_right(self.kept_starts, index) - 1
        return self.starts[run] + index - self.kept_starts[run]


def blind(text: str, anchor: str) -> tuple[Match, ...]:
    """Every place anchor appears once spaces and tabs are ignored on both sides. An anchor that starts with
    spaces or tabs takes the indent before the match too, and never starts right after another character, so
    its first word never matches the end of a longer one. One that ends with them takes the spaces after."""
    squeezed, wanted = Squeezed.of(text), WORD_RUN.findall(anchor)
    needle = "".join(wanted)
    if not needle:
        return ()
    found, at = [], squeezed.text.find(needle)
    while at >= 0:
        start = squeezed.original(at)
        end = squeezed.original(at + len(needle) - 1) + 1
        if anchor[0] in " \t":
            if start > 0 and text[start - 1] not in " \t\n":
                at = squeezed.text.find(needle, at + 1)
                continue
            while start > 0 and text[start - 1] in " \t":
                start -= 1
        if anchor[-1] in " \t":
            while end < len(text) and text[end] in " \t":
                end += 1
        found.append(match_at(text, start, end))
        at = squeezed.text.find(needle, at + len(needle))
    return tuple(found)


def closest(text: str, anchor: str, limit: int = 3) -> tuple[Candidate, ...]:
    """The places anchor nearly matches, best first: every match with spaces and tabs ignored, or else up to
    limit windows of the file's lines that score at least FUZZY_FLOOR."""
    exact = [Candidate(match, text[match.start:match.end], 1.0, True) for match in blind(text, anchor)]
    if exact:
        return tuple(exact)
    return fuzzy(text, anchor, limit)


def normal(line: str) -> str:
    return SPACE_RUN.sub(" ", line).strip()


def fuzzy(text: str, anchor: str, limit: int) -> tuple[Candidate, ...]:
    """The windows of len(anchor's lines) file lines most like anchor, found from the file lines most like
    anchor's longest line."""
    lines = text.split("\n")
    wanted = anchor.strip("\n").split("\n")
    if len(lines) > FUZZY_LINES or not any(normal(line) for line in wanted):
        return ()
    key = max(range(len(wanted)), key=lambda index: len(normal(wanted[index])))
    normals = [normal(line) for line in lines]
    seeds = difflib.get_close_matches(normal(wanted[key]), normals, n=20, cutoff=0.4)
    starts = sorted({index - key for index, line in enumerate(normals) if line in seeds})[:FUZZY_STARTS]
    goal = "\n".join(normal(line) for line in wanted)
    scored = []
    for start in (start for start in starts if 0 <= start <= len(lines) - len(wanted)):
        matcher = difflib.SequenceMatcher(None, goal, "\n".join(normals[start:start + len(wanted)]),
                                          autojunk=False)
        if matcher.real_quick_ratio() < FUZZY_FLOOR or matcher.quick_ratio() < FUZZY_FLOOR:
            continue
        score = matcher.ratio()
        if score >= FUZZY_FLOOR:
            scored.append((score, start))
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)
    found: list[Candidate] = []
    for score, start in sorted(scored, key=lambda pair: (-pair[0], pair[1])):
        if any(abs(start - (other.match.first_line - 1)) < len(wanted) for other in found):
            continue
        end = start + len(wanted)
        begin, finish = offsets[start], offsets[end] - 1
        found.append(Candidate(Match(begin, finish, start + 1, end), text[begin:finish], round(score, 3),
                               False))
        if len(found) == limit:
            break
    return tuple(found)


def unique_anchor(text: str, match: Match) -> str:
    """The shortest run of whole lines around match that appears once in text: the match's own lines, then
    one more line below and above in turn."""
    lines = text.split("\n")
    first, last = match.first_line - 1, match.last_line - 1
    below = True
    while True:
        candidate = "\n".join(lines[first:last + 1])
        if text.count(candidate) == 1 or (first == 0 and last == len(lines) - 1):
            return candidate
        if (below and last < len(lines) - 1) or first == 0:
            last += 1
        else:
            first -= 1
        below = not below
