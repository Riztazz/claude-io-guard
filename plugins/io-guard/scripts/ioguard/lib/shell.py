"""Reading a Bash command the way bash will: its heredocs, its python -c bodies, the backslash pairs the
Windows Bash tool halves, and its length as that tool's transport counts it.

The scanner follows bash's quoting: single quotes, double quotes and their four escapes, $'...' strings,
command substitution, arithmetic, comments and heredoc bodies. It holds no policy. checks.transport_body
decides what to move and what to refuse.
"""
import json
import re
import shlex
from dataclasses import dataclass

NORMAL, SINGLE, DOUBLE, ANSI, COMMENT, BODY, ARITH = range(7)
ESCAPED_IN_DOUBLE = "$`\"\\\n"          # a backslash escapes only these inside double quotes
ESCAPED_IN_BODY = "$`\\\n"              # and only these in a heredoc body bash expands
WORD_END = " \t\n;&|<>()"
COMMAND_START = r"(?:^|[;&|(\n])[ \t]*(?:[A-Za-z_]\w*=\S*[ \t]+)*"
PYTHON_NAME = r"py(?:thon[\d.]*)?(?:\.exe)?"
PROGRAM = (rf"(?P<program>\"(?:[^\"]*[\\/])?{PYTHON_NAME}\"|'(?:[^']*[\\/])?{PYTHON_NAME}'"
           rf"|(?:[^\s;&|()<>'\"]*[\\/])?{PYTHON_NAME})")
PYTHON_C = re.compile(COMMAND_START + PROGRAM + r"(?:[ \t]+-[A-Za-z0-9]+)*[ \t]+-c[ \t]+(?P<quote>['\"])",
                      re.I)


@dataclass(frozen=True)
class Heredoc:
    operator: tuple[int, int]    # the <<'X' text
    delimiter: str
    quoted: bool                 # any quote in the delimiter word, so bash expands nothing in the body
    strip_tabs: bool             # <<- drops the leading tabs of each line
    body: str                    # what the command reads, tabs already dropped for <<-
    span: tuple[int, int]        # from the first body line through the delimiter line and its newline
    terminated: bool             # the delimiter line was found


@dataclass(frozen=True)
class InlineBody:
    program: str                 # the python word as written
    argument: tuple[int, int]    # the quoted -c argument, quotes included
    body: str                    # the argument as bash passes it
    expands: bool                # a $ or a backtick inside double quotes, which bash expands


@dataclass(frozen=True)
class Scan:
    heredocs: tuple[Heredoc, ...]
    bodies: tuple[InlineBody, ...]
    hazards: tuple[int, ...]     # offsets of the \\ pairs whose halving changes what bash reads
    states: bytes                # the quoting state at each offset


class Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.states = bytearray(len(text))
        self.hazards: list[int] = []
        self.heredocs: list[Heredoc] = []
        self.pending: list[tuple[int, int, str, bool, bool]] = []

    def mark(self, start: int, end: int, state: int) -> None:
        self.states[start:end] = bytes([state]) * (end - start)

    def pair(self, at: int) -> bool:
        """Whether the Windows Bash tool halves the pair at at: its run of backslashes is followed by
        something other than a double quote. A run before a double quote, or at the end, arrives whole."""
        if not self.text.startswith("\\\\", at):
            return False
        end = at
        while end < len(self.text) and self.text[end] == "\\":
            end += 1
        return end < len(self.text) and self.text[end] != '"'

    def run(self) -> Scan:
        self.normal(0, stop=None)
        return Scan(tuple(self.heredocs), inline_bodies(self.text, self.states), tuple(sorted(self.hazards)),
                    bytes(self.states))

    def normal(self, at: int, stop: str | None) -> int:
        """Scan unquoted text from at, until stop closes a command substitution. Returns the offset after."""
        text, depth = self.text, 0
        while at < len(text):
            char = text[at]
            if char == "\\":
                if self.pair(at):
                    self.hazards.append(at)
                at += 2
            elif char == "'":
                at = self.single(at + 1)
            elif char == '"':
                at = self.double(at + 1)
            elif text.startswith("$((", at):
                at = self.arithmetic(at)
            elif text.startswith("$'", at):
                at = self.ansi(at + 2)
            elif text.startswith("$(", at):
                at = self.normal(at + 2, stop=")")
            elif char == "(" and stop:
                depth, at = depth + 1, at + 1
            elif char == ")" and stop:
                if depth == 0:
                    return at + 1
                depth, at = depth - 1, at + 1
            elif char == "#" and (at == 0 or text[at - 1] in " \t\n;&|()"):
                end = text.find("\n", at)
                end = len(text) if end < 0 else end
                self.mark(at, end, COMMENT)
                at = end
            elif text.startswith("<<", at) and not text.startswith("<<<", at):
                at = self.operator(at)
            elif char == "\n" and self.pending:
                at = self.bodies(at + 1)
            else:
                at += 1
        return at

    def single(self, at: int) -> int:
        end = self.text.find("'", at)
        end = len(self.text) if end < 0 else end
        self.mark(at, end, SINGLE)
        self.hazards.extend(offset for match in re.finditer(r"\\\\", self.text[at:end])
                            if self.pair(offset := at + match.start()))
        return end + 1

    def double(self, at: int) -> int:
        text = self.text
        while at < len(text):
            char = text[at]
            if char == '"':
                return at + 1
            if char == "\\" and at + 1 < len(text) and text[at + 1] in ESCAPED_IN_DOUBLE:
                if self.pair(at) and at + 2 < len(text) and text[at + 2] in ESCAPED_IN_DOUBLE:
                    self.hazards.append(at)
                self.mark(at, at + 2, DOUBLE)
                at += 2
            elif text.startswith("$((", at):
                at = self.arithmetic(at)
            elif text.startswith("$(", at):
                at = self.normal(at + 2, stop=")")
            else:
                self.states[at] = DOUBLE
                at += 1
        return at

    def ansi(self, at: int) -> int:
        text = self.text
        while at < len(text) and text[at] != "'":
            if text[at] == "\\":
                if self.pair(at):
                    self.hazards.append(at)
                self.mark(at, at + 2, ANSI)
                at += 2
            else:
                self.states[at] = ANSI
                at += 1
        return at + 1

    def arithmetic(self, at: int) -> int:
        depth, end = 0, at + 1
        while end < len(self.text):
            if self.text[end] == "(":
                depth += 1
            elif self.text[end] == ")":
                depth -= 1
                if depth == 0:
                    end += 1
                    break
            end += 1
        self.mark(at, end, ARITH)
        return end

    def operator(self, at: int) -> int:
        """A heredoc operator: record its delimiter, whose body starts on the next line."""
        text, end = self.text, at + 2
        strip = text.startswith("-", end)
        end += strip
        while end < len(text) and text[end] in " \t":
            end += 1
        word, quoted, start = [], False, end
        while end < len(text) and text[end] not in WORD_END:
            char = text[end]
            if char in "'\"":
                close = text.find(char, end + 1)
                close = len(text) if close < 0 else close
                word.append(text[end + 1:close])
                quoted, end = True, close + 1
            elif char == "\\":
                word.append(text[end + 1:end + 2])
                quoted, end = True, end + 2
            else:
                word.append(char)
                end += 1
        if end > start:
            self.pending.append((at, end, "".join(word), quoted, strip))
        return max(end, at + 2)

    def bodies(self, at: int) -> int:
        """Read the body of each heredoc waiting for this line, in order, and return the offset after them."""
        text = self.text
        for operator_start, operator_end, delimiter, quoted, strip in self.pending:
            start, lines, terminated = at, [], False
            while at < len(text):
                newline = text.find("\n", at)
                end = len(text) if newline < 0 else newline + 1
                line = text[at:end].rstrip("\n")
                at = end
                if (line.lstrip("\t") if strip else line) == delimiter:
                    terminated = True
                    break
                lines.append((line.lstrip("\t") if strip else line) + ("\n" if newline >= 0 else ""))
            self.mark(start, at, BODY)
            self.body_hazards(start, at, quoted)
            self.heredocs.append(Heredoc((operator_start, operator_end), delimiter, quoted, strip,
                                         "".join(lines), (start, at), terminated))
        self.pending = []
        return at

    def body_hazards(self, start: int, end: int, quoted: bool) -> None:
        for match in re.finditer(r"\\\\", self.text[start:end]):
            after = self.text[start + match.end():start + match.end() + 1]
            if self.pair(start + match.start()) and (quoted or after in ESCAPED_IN_BODY):
                self.hazards.append(start + match.start())


def inline_bodies(text: str, states: bytes | bytearray) -> tuple[InlineBody, ...]:
    """Each python -c whose argument is one quoted string, in unquoted text."""
    found = []
    for match in PYTHON_C.finditer(text):
        program, quote = match.start("program"), match.start("quote")
        if states[program] != NORMAL or states[quote] != NORMAL:
            continue
        parsed = quoted_word(text, quote)
        if parsed is not None:
            end, body, expands = parsed
            found.append(InlineBody(match["program"], (quote, end), body, expands))
    return tuple(found)


def quoted_word(text: str, at: int) -> tuple[int, str, bool] | None:
    """The quoted string at at, when it is the whole word: its end, what bash passes, and whether bash
    expands anything in it. None for an unclosed string or a word that goes on past the quote."""
    if text[at] == "'":
        close = text.find("'", at + 1)
        if close < 0:
            return None
        end, body, expands = close + 1, text[at + 1:close], False
    else:
        parts, index, expands = [], at + 1, False
        while index < len(text) and text[index] != '"':
            char = text[index]
            if char == "\\" and index + 1 < len(text) and text[index + 1] in ESCAPED_IN_DOUBLE:
                parts.append("" if text[index + 1] == "\n" else text[index + 1])
                index += 2
                continue
            expands = expands or char in "$`"
            parts.append(char)
            index += 1
        if index >= len(text):
            return None
        end, body = index + 1, "".join(parts)
    if end < len(text) and text[end] not in WORD_END:
        return None
    return end, body, expands


def scan(command: str) -> Scan:
    return Scanner(command).run()


def budget_length(command: str) -> int:
    """The command's length as the Windows Bash tool's transport counts it: UTF-8 bytes, and each apostrophe
    as four, which is how the baseline's largest passing and smallest failing commands line up."""
    return len(command.encode("utf-8")) + 3 * command.count("'")


def shell_path(path: str) -> str:
    """A path as a bash word in double quotes, escaping the four characters bash reads there."""
    return '"' + re.sub(r'([$`"\\])', r"\\\1", path) + '"'


def exec_file(path: str) -> str:
    """A python -c argument that runs the file as the -c body would have run: in __main__, with sys.argv and
    sys.path[0] left as -c sets them, and tracebacks naming the file."""
    quoted = json.dumps(path)
    return shlex.quote(f"exec(compile(open({quoted}, encoding=\"utf-8\").read(), {quoted}, \"exec\"))")


def moved(command: str, heredocs: dict[Heredoc, str], bodies: dict[InlineBody, str]) -> str:
    """The command with each heredoc read from its file through a stdin redirect, and each python -c body
    run from its file. Everything else stays exactly as written."""
    edits = [(heredoc.span, "") for heredoc in heredocs]
    edits += [(heredoc.operator, "< " + shell_path(path)) for heredoc, path in heredocs.items()]
    edits += [(body.argument, exec_file(path)) for body, path in bodies.items()]
    for (start, end), replacement in sorted(edits, key=lambda edit: edit[0][0], reverse=True):
        command = command[:start] + replacement + command[end:]
    return command
