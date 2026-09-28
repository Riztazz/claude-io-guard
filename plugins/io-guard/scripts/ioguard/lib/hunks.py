"""The hunks of one file's git diff, as bytes, and a patch of the ones chosen, for staging part of a file with
no prompt (GIT-4).

git add -p asks at a prompt, so agents replayed their own transcripts to stage one task's hunks. parse reads
git diff -U0 of one file, where every change is its own hunk and no context joins two, and patch writes back
the head with the hunks chosen, byte for byte, for git apply --cached. A hunk keeps its lines as git gave
them, endings and all, so the index takes exactly the bytes the diff carried (BYT-10).
"""
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from ioguard.lib.journal import key, text_of

HEADER = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Hunk:
    header: bytes
    body: tuple[bytes, ...]          # each line after the header, with its ending, the no-newline note too
    old_start: int
    old_count: int
    new_start: int
    new_count: int

    def lines(self) -> tuple[int, int]:
        """The lines of the file now that the hunk covers, from 1. A pure deletion sits at the line after
        it."""
        if self.new_count == 0:
            return self.new_start + 1, self.new_start + 1
        return self.new_start, self.new_start + self.new_count - 1

    def changed(self, sign: bytes) -> list[str]:
        return [text_of(line[1:]) for line in self.body if line.startswith(sign)]

    def meets(self, first: int, last: int) -> bool:
        start, end = self.lines()
        return start <= last and first <= end


@dataclass(frozen=True)
class FileDiff:
    head: bytes                      # the diff --git, index, --- and +++ lines
    hunks: tuple[Hunk, ...]
    binary: bool


def parse(raw: bytes) -> FileDiff | None:
    """One file's diff, or None when git reported no change."""
    if not raw.strip():
        return None
    lines = raw.splitlines(keepends=True)
    at = next((index for index, line in enumerate(lines) if line.startswith(b"@@")), len(lines))
    head = b"".join(lines[:at])
    hunks, current = [], None
    for line in lines[at:]:
        found = HEADER.match(line)
        if found:
            old_start, old_count, new_start, new_count = found.groups()
            current = [line, [], int(old_start), 1 if old_count is None else int(old_count), int(new_start),
                       1 if new_count is None else int(new_count)]
            hunks.append(current)
        elif current is not None:
            current[1].append(line)
    binary = b"Binary files " in head or b"GIT binary patch" in head
    return FileDiff(head, tuple(Hunk(each[0], tuple(each[1]), *each[2:]) for each in hunks), binary)


def patch(diff: FileDiff, chosen: Sequence[Hunk]) -> bytes:
    return diff.head + b"".join(hunk.header + b"".join(hunk.body) for hunk in chosen)


def trivial(line: str) -> bool:
    """A line any task could have written: blank, or punctuation alone, such as a brace."""
    return not any(char.isalnum() for char in line)


@dataclass(frozen=True)
class Owned:
    hunk: Hunk
    mine: bool                       # every line that says anything is one the task wrote or removed
    mixed: bool                      # some are the task's and some are not


def owned(hunk: Hunk, added: Collection[str], removed: Collection[str]) -> Owned:
    """Whether the hunk is a task's, from the keys of the lines the journal says it added and removed. Lines
    that say nothing, such as a brace, count only in a hunk that holds nothing else."""
    lines = [(line, added) for line in hunk.changed(b"+")] + [(line, removed) for line in hunk.changed(b"-")]
    telling = [(line, keys) for line, keys in lines if not trivial(line)] or lines
    hits = [key(line) in keys for line, keys in telling]
    return Owned(hunk, bool(hits) and all(hits), any(hits) and not all(hits))
