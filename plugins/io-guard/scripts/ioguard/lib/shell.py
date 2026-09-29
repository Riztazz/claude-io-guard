"""Reading a Bash command the way bash will: its heredocs, its python -c bodies, the backslash pairs the
Windows Bash tool halves, its simple commands, the quoting that bash reads differently from what was meant,
and its length as that tool's transport counts it.

The scanner follows bash's quoting: single quotes, double quotes and their four escapes, $'...' strings,
command substitution, arithmetic, comments and heredoc bodies. It holds no policy. The checks decide what to
move, rewrite and refuse.
"""
import json
import re
import shlex
from collections.abc import Sequence
from dataclasses import dataclass

NORMAL, SINGLE, DOUBLE, ANSI, COMMENT, BODY, ARITH = range(7)
MAX_NESTING = 100                       # $( ... ) levels read, well inside Python's stack
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
    backticks: tuple[int, ...] = ()   # offsets of unescaped backticks inside double quotes
    unterminated: bool = False        # a quote runs to the end, so bash stops at unexpected EOF
    too_deep: bool = False            # $( ... ) nests past MAX_NESTING, and the scan stopped there


class Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.states = bytearray(len(text))
        self.hazards: list[int] = []
        self.backticks: list[int] = []
        self.unclosed = False
        self.heredocs: list[Heredoc] = []
        self.pending: list[tuple[int, int, str, bool, bool]] = []
        self.depth, self.too_deep = 0, False

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
                    bytes(self.states), tuple(self.backticks), self.unclosed, self.too_deep)

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
                at = self.arithmetic(at, at + 1)
            elif text.startswith("((", at) and self.command_position(at):
                at = self.arithmetic(at, at)
            elif text.startswith("$'", at):
                at = self.ansi(at + 2)
            elif text.startswith("$(", at):
                at = self.substitution(at)
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

    def substitution(self, at: int) -> int:
        """The $( ... ) at at, one level deeper. Past MAX_NESTING levels the scan stops there, marked too
        deep, so the scanner never runs out of stack. Returns the offset after."""
        if self.depth >= MAX_NESTING:
            self.too_deep = True
            return len(self.text)
        self.depth += 1
        try:
            return self.normal(at + 2, stop=")")
        finally:
            self.depth -= 1

    def single(self, at: int) -> int:
        end = self.text.find("'", at)
        if end < 0:
            end, self.unclosed = len(self.text), True
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
                at = self.arithmetic(at, at + 1)
            elif text.startswith("$(", at):
                at = self.substitution(at)
            else:
                if char == "`":
                    self.backticks.append(at)
                self.states[at] = DOUBLE
                at += 1
        self.unclosed = True
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
        self.unclosed = self.unclosed or at >= len(text)
        return at + 1

    def command_position(self, at: int) -> bool:
        """Whether at starts a command, where bash reads (( as arithmetic: after nothing, an operator, a
        newline or for."""
        text, back = self.text, at
        while back > 0 and text[back - 1] in " \t":
            back -= 1
        return (back == 0 or text[back - 1] in ";&|(\n"
                or (back >= 3 and text.startswith("for", back - 3)
                    and (back == 3 or text[back - 4] in " \t\n;&|(")))

    def arithmetic(self, at: int, opening: int) -> int:
        """$(( ... )) or (( ... )) from at, whose first parenthesis is at opening. The offset after it."""
        depth, end = 0, opening
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
            if char == "$" and text[end + 1:end + 2] in ("'", '"'):
                end += 1
            elif char in "'\"":
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


@dataclass(frozen=True)
class Redirect:
    target: str                  # the word after the operator, quotes removed
    append: bool                 # >> or &>>
    fd: int | None               # the stream it names, None for &> which names both


@dataclass(frozen=True)
class SimpleCommand:
    words: tuple[str, ...]       # quotes removed, with leading assignments and reserved words dropped
    redirects: tuple[Redirect, ...]   # the output redirects to a file, never a duplicated stream
    inputs: tuple[str, ...]      # the files a < redirect reads
    span: tuple[int, int]

    @property
    def name(self) -> str:
        """The program's name, without its folder or .exe."""
        if not self.words:
            return ""
        name = re.split(r"[\\/]", self.words[0])[-1]
        return name[:-4].lower() if name.lower().endswith(".exe") else name.lower()


SEPARATORS = ";&|\n()"
RESERVED = {"if", "then", "else", "elif", "fi", "do", "done", "while", "until", "for", "case", "esac", "in",
            "{", "}", "!", "time", "exec", "command", "builtin", "nohup", "sudo"}
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
REDIRECT = re.compile(r"(\d*|&)(>>?|>\||<>?)")


def commands(command: str, found: Scan | None = None) -> tuple[SimpleCommand, ...]:
    """The simple commands of a Bash command, split at the operators bash reads outside quotes, heredoc bodies
    and comments. Command substitutions stay inside their word."""
    found = found or scan(command)
    states, text = found.states, command
    parsed, at, start = [], 0, 0
    words: list[str] = []
    redirects: list[Redirect] = []
    inputs: list[str] = []

    def finish(end: int) -> None:
        nonlocal words, redirects, inputs
        kept = list(words)
        while kept and (ASSIGNMENT.match(kept[0]) or kept[0] in RESERVED):
            kept.pop(0)
        if kept or redirects:
            parsed.append(SimpleCommand(tuple(kept), tuple(redirects), tuple(inputs), (start, end)))
        words, redirects, inputs = [], [], []

    while at < len(text):
        char = text[at]
        normal = states[at] == NORMAL
        match = REDIRECT.match(text, at) if normal and not text.startswith("<<", at) else None
        if normal and char in SEPARATORS and not match:
            finish(at)
            at += 1
            start = at
        elif (normal and char in " \t") or states[at] in (COMMENT, BODY):
            at += 1
        elif normal and text.startswith("\\\n", at):
            at += 2
        elif match:
            at = match.end()
            if text.startswith("&", at):          # 2>&1, >&2: a duplicated stream, not a file
                at = word_end(text, states, at + 1)
                continue
            while at < len(text) and text[at] in " \t":
                at += 1
            end = word_end(text, states, at)
            target = unquote(text, states, at, end)
            operator = match[2]
            if operator.startswith(">"):
                fd = None if match[1] == "&" else int(match[1] or 1)
                redirects.append(Redirect(target, operator == ">>", fd))
            else:
                inputs.append(target)
            at = end
        elif states[at] == NORMAL and text.startswith("<<", at):
            at = heredoc_word_end(text, at)
        else:
            end = word_end(text, states, at)
            words.append(unquote(text, states, at, end))
            at = end
    finish(len(text))
    return tuple(parsed)


def word_end(text: str, states: bytes | bytearray, at: int) -> int:
    """The end of the word starting at at: the first unquoted blank, operator or redirect."""
    while at < len(text):
        if states[at] == NORMAL:
            if text[at] in " \t" or text[at] in SEPARATORS or text[at] in "<>":
                if not (text[at] in "()" and text.startswith("$(", at - 1)):
                    return at
            if text[at] == "\\":
                at += 2
                continue
            if text.startswith("$(", at):
                depth, at = 1, at + 2
                while at < len(text) and depth:
                    depth += {"(": 1, ")": -1}.get(text[at], 0) if states[at] == NORMAL else 0
                    at += 1
                continue
        elif states[at] in (COMMENT, BODY):
            return at
        at += 1
    return at


def heredoc_word_end(text: str, at: int) -> int:
    at += 2
    at += text.startswith("-", at)
    while at < len(text) and text[at] in " \t":
        at += 1
    while at < len(text) and text[at] not in WORD_END:
        at += 1
    return at


def unquote(text: str, states: bytes | bytearray, start: int, end: int) -> str:
    """The word as bash passes it, for the plain cases: quotes dropped, escapes applied, expansions kept. A
    backslash before a newline joins the lines, so both go."""
    out, at = [], start
    while at < end:
        char, state = text[at], states[at]
        if state == NORMAL and char in "'\"":
            at += 1
        elif char == "\\" and at + 1 < end and (state == NORMAL or (state == DOUBLE
                                                                   and text[at + 1] in ESCAPED_IN_DOUBLE)):
            out.append("" if text[at + 1] == "\n" else text[at + 1])
            at += 2
        else:
            out.append(char)
            at += 1
    return "".join(out)


def blanked(command: str, found: Scan | None = None) -> str:
    """The command with the text inside each pair of quotes, each comment and each heredoc body turned into
    spaces, so a search of what is left finds only code. The quote marks stay, and every offset still points
    at the same place."""
    states = (found or scan(command)).states
    return "".join(char if states[at] == NORMAL or char == "\n" else " " for at, char in enumerate(command))


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


# A match starts only where a token starts, so a long token is scanned once, not once from each character
BODY_FILE = re.compile(r"(?<![^\s'\"<>])[^\s'\"<>]*(?:io-guard|bodies)/body-[0-9a-f]{16}\.(?:txt|py)")
PYTHON = re.compile(rf"^{PYTHON_NAME}$", re.I)
INTERPRETERS = re.compile(r"^(?:python[\d.]*|py|node|perl|ruby)$")
INLINE = {"-c", "-m", "-", "-e", "--eval", "-p", "--print"}   # the flags that run no script file
TAKES_VALUE = {"-W", "-X"}


@dataclass(frozen=True)
class ScriptRun:
    """An interpreter running a script file: the file as the command names it, and the words after it."""
    script: str
    arguments: tuple[str, ...]


def script_run(simple: SimpleCommand) -> ScriptRun | None:
    """The script file an interpreter runs, or None for an inline program, a module, stdin, or no script."""
    if not INTERPRETERS.match(simple.name):
        return None
    words, at = simple.words[1:], 0
    while at < len(words) and words[at].startswith("-"):
        if words[at] in INLINE:
            return None
        at += 2 if words[at] in TAKES_VALUE else 1
    return ScriptRun(words[at], tuple(words[at + 1:])) if at < len(words) else None
QUOTED_PATH_BEFORE_QUOTE = re.compile(r'"[A-Za-z]:\\[^"\n]*\\"(?=[\s;&|)<>]|$)')


def body_files(command: str) -> tuple[str, ...]:
    """The body files a moved command reads, named io-guard/body-<16 hex>.txt or .py."""
    return tuple(match[0] for match in BODY_FILE.finditer(command))


def python_reads_stdin(simple: SimpleCommand) -> bool:
    """Whether the simple command is Python reading its program from stdin: no script, no -c and no -m."""
    if not PYTHON.match(simple.name):
        return False
    words = iter(simple.words[1:])
    for word in words:
        if word == "-":
            return True
        if word in ("-c", "-m") or not word.startswith("-"):
            return False
        if word in ("-W", "-X"):
            next(words, None)
    return True


def piped(command: str, simple: SimpleCommand) -> bool:
    """Whether the simple command's output goes into a pipe: one | or a |& follows it."""
    end = simple.span[1]
    return command[end:end + 1] == "|" and command[end + 1:end + 2] != "|"


def matching(simple: SimpleCommand, entries: Sequence[str]) -> str | None:
    """The command simple runs, as the first entry of entries its words start with, such as make or
    python -m pytest. Case and a folder or .exe on the program are ignored. None when no entry fits."""
    for entry in entries:
        words = entry.lower().split()
        head = re.split(r"[\\/]", words[0])[-1].removesuffix(".exe")
        named = PYTHON.match(simple.name) if head == "python" else simple.name == head
        if named and [word.lower() for word in simple.words[1:len(words)]] == words[1:]:
            return " ".join(simple.words[:len(words)])
    return None


@dataclass(frozen=True)
class Pipeline:
    commands: tuple[SimpleCommand, ...]
    joined_by: str               # "&&", "||" or ";" to the pipeline before, "" for the first


GROUPING = frozenset({"if", "then", "else", "elif", "fi", "case", "esac", "{", "}", "!", "(", ")"})
JOINS = re.compile(r"&&|\|\||\||[;&\n(){}]|[^\s;&|(){}]+")
OPERATORS = frozenset({"&&", "||", "|", ";", "&", "\n"})
LOOP_WORDS = frozenset({"do", "done"})


def pipelines(command: str, found: Scan | None = None) -> tuple[Pipeline, ...] | None:
    """The pipelines of a Bash command in order, each with the operator that joins it to the one before. None
    when parentheses, braces, if, case or ! group its commands, or when a command made only of assignments
    ends the command or joins the next with &&, || or |, because the order alone then no longer says which
    command ran last."""
    found = found or scan(command)
    simples = commands(command, found)
    if not simples:
        return ()
    top = structure(command, found.states)

    def normal(start: int, end: int) -> str:
        return "".join(command[at] if top[at] else " " for at in range(start, end))

    bounds = [0, *(point for simple in simples for point in simple.span), len(command)]
    joins = [JOINS.findall(normal(start, end)) for start, end in zip(bounds[::2], bounds[1::2])]
    firsts = [normal(*simple.span).split(None, 1)[:1] for simple in simples]
    if any(GROUPING & set(tokens) for tokens in joins) or any(GROUPING & set(first) for first in firsts):
        return None
    for tokens in joins:
        words = [index for index, token in enumerate(tokens) if token not in OPERATORS | LOOP_WORDS]
        after = next((token for token in tokens[words[-1]:] if token in OPERATORS), None) if words else ";"
        if after in (None, "&&", "||", "|"):
            return None
    found_lines, current, joined = [], [simples[0]], ""
    for simple, tokens in zip(simples[1:], joins[1:-1]):
        kind = next((mark for mark in ("&&", "||", "|") if mark in tokens), ";")
        if kind == "|":
            current.append(simple)
            continue
        found_lines.append(Pipeline(tuple(current), joined))
        current, joined = [simple], kind
    found_lines.append(Pipeline(tuple(current), joined))
    return tuple(found_lines)


def structure(command: str, states: bytes) -> bytearray:
    """1 for each character bash reads as the command's own structure: outside quotes, comments, heredoc
    bodies and every $( ) or ${ } expansion."""
    top, depth, at = bytearray(len(command)), 0, 0
    while at < len(command):
        char = command[at]
        if states[at] != NORMAL:
            at += 1
            continue
        if command.startswith(("$(", "${"), at):
            depth, at = depth + 1, at + 2
            continue
        if depth and char in "({":
            depth += 1
        elif depth and char in ")}":
            depth -= 1
        elif not depth:
            top[at] = 1
        at += 1
    return top


def exit_candidates(command: str, found: Scan | None = None) -> tuple[SimpleCommand, ...]:
    """The simple commands whose exit code can be the whole command's, the last to run first: the last command
    of each pipeline in the && chain that ends the command, or every command of those pipelines under
    pipefail. () when pipelines cannot say."""
    lines = pipelines(command, found)
    chosen: list[SimpleCommand] = []
    for line in reversed(lines or ()):
        chosen += reversed(line.commands) if "pipefail" in command else [line.commands[-1]]
        if line.joined_by != "&&":
            break
    return tuple(chosen)


def call_operators(command: str, states: bytes) -> tuple[int, ...]:
    """The offsets of each & that starts a command, as PowerShell's call operator does. Bash reads one as a
    syntax error. The & of &&, |&, 2>&1 and &> is never one."""
    found = []
    for at, char in enumerate(command):
        if char != "&" or states[at] != NORMAL or command[at - 1:at] in ("&", ">", "<", "|"):
            continue
        if command[at + 1:at + 2] in ("&", ">"):
            continue
        before = command[:at].rstrip(" \t")
        if not before or before[-1] in "\n;(|&":
            found.append(at)
    return tuple(found)


def trailing_backslash_paths(command: str) -> tuple[tuple[int, int], ...]:
    """The spans of the double-quoted Windows paths that end in a backslash. That backslash escapes the
    closing quote, so bash reads the string on past it."""
    return tuple(match.span() for match in QUOTED_PATH_BEFORE_QUOTE.finditer(command))


def forward_slashed(command: str, spans: Sequence[tuple[int, int]]) -> str:
    """The command with each backslash inside the spans turned into a forward slash."""
    for start, end in sorted(spans, reverse=True):
        command = command[:start] + command[start:end].replace("\\", "/") + command[end:]
    return command
