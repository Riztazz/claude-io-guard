"""A source file as the code a comment or include pass must leave alone: its tokens with comments and layout
dropped, or its lines with the include lines taken out (VFY-6).

Agents proved a comment-only pass changed no code with a checker each pass built again. code_tokens gives the
tokens of a C-family, Python or hash-comment file, so two versions compare equal when they differ only in
comments, whitespace and line breaks. Python goes through its own tokenizer, with docstrings counted as
comments and indentation kept, since it is code there. A file of another kind has no rules, and the caller
compares its bytes. split_includes gives the include lines of a file apart from the rest, for a pass that only
sorts or trims includes.
"""
import io
import re
import tokenize
from dataclasses import dataclass

from ioguard.lib.text import BOM_CHAR

C_FAMILY = frozenset({".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp", ".cs",
                      ".java", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".swift", ".kt", ".kts", ".m",
                      ".mm", ".usf", ".ush", ".hlsl", ".glsl"})
PYTHON = frozenset({".py", ".pyi"})
HASH = frozenset({".sh", ".bash", ".ps1", ".psm1", ".yml", ".yaml", ".toml", ".cmake", ".rb", ".pl", ".r"})
INCLUDE = {**{suffix: re.compile(r"\s*#\s*(include|import)\b") for suffix in C_FAMILY},
           ".cs": re.compile(r"\s*(global\s+)?using\s+[\w.]+(\s*=\s*[\w.<>]+)?\s*;"),
           ".java": re.compile(r"\s*import\s"), ".kt": re.compile(r"\s*import\s"),
           ".kts": re.compile(r"\s*import\s"), ".swift": re.compile(r"\s*import\s"),
           ".go": re.compile(r"\s*import\s"), ".rs": re.compile(r"\s*(pub\s+)?use\s"),
           ".js": re.compile(r"\s*import\s.*\bfrom\b|\s*import\s+['\"]"),
           ".ts": re.compile(r"\s*import\s.*\bfrom\b|\s*import\s+['\"]"),
           **{suffix: re.compile(r"\s*(import|from)\s+[\w.]+") for suffix in PYTHON}}
C_TOKEN = re.compile(r'R"(?P<delim>[^(\s]{0,16})\((?:.|\n)*?\)(?P=delim)"'   # a C++ raw string
                     r'|@"(?:[^"]|"")*"'                                    # a C# verbatim string
                     r'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`'
                     r"|//[^\n]*|/\*(?:.|\n)*?\*/"
                     r"|\w+|\s+|.", re.MULTILINE)
HASH_TOKEN = re.compile(r'"(?:\\.|[^"\\\n])*"|\'[^\'\n]*\'|<#(?:.|\n)*?#>|#[^\n]*|\w+|\s+|.')
LAYOUT = frozenset({tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENCODING, tokenize.ENDMARKER})


@dataclass(frozen=True)
class Token:
    line: int                        # the line it starts on, from 1
    text: str                        # the token, or its kind alone for Python's indent and dedent


def code_tokens(text: str, suffix: str) -> tuple[Token, ...] | None:
    """The code in text as tokens, or None when io-guard has no comment rules for suffix."""
    suffix, text = suffix.lower(), text.removeprefix(BOM_CHAR)
    if suffix in PYTHON:
        return python_tokens(text)
    if suffix in C_FAMILY:
        return scanned(text, C_TOKEN, comments=("//", "/*"))
    if suffix in HASH:
        return scanned(text, HASH_TOKEN, comments=("#", "<#"))
    return None


def scanned(text: str, pattern: re.Pattern, comments: tuple[str, ...]) -> tuple[Token, ...]:
    found, line = [], 1
    for match in pattern.finditer(text):
        piece = match[0]
        if not piece.isspace() and not piece.startswith(comments):
            found.append(Token(line, piece))
        line += piece.count("\n")
    return tuple(found)


def python_tokens(text: str) -> tuple[Token, ...]:
    """Python's own tokens less comments, line breaks and docstrings, with indent and dedent kept as kinds. A
    file Python cannot tokenize is read as a hash-comment file. The 3.14 tokenizer raises more than
    TokenError on text it cannot read: a UnicodeDecodeError for a lone CR before a non-ASCII character, a
    UnicodeEncodeError for a lone surrogate, and a SystemError under fuzzing, so any failure falls back."""
    try:
        raw = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except Exception:
        return scanned(text, HASH_TOKEN, comments=("#",))
    kinds = (tokenize.INDENT, tokenize.DEDENT)
    significant = [token for token in raw if token.type not in (tokenize.NL, tokenize.COMMENT)]
    found: list[Token] = []
    for index, token in enumerate(significant):
        if token.type in LAYOUT or docstring(significant, index):
            continue
        shown = tokenize.tok_name[token.type] if token.type in kinds else token.string
        found.append(Token(token.start[0], shown))
    return tuple(found)


def docstring(significant: list[tokenize.TokenInfo], index: int) -> bool:
    """Whether the token at index, among the tokens that are not comments or blank lines, is a string that
    stands alone as the first statement of a module or of a block, such as a class or a function body."""
    if significant[index].type != tokenize.STRING:
        return False
    after = significant[index + 1] if index + 1 < len(significant) else None
    alone = after is None or after.type in (tokenize.NEWLINE, tokenize.ENDMARKER)
    first = index == 0 or significant[index - 1].type in (tokenize.ENCODING, tokenize.INDENT)
    return alone and first


@dataclass(frozen=True)
class Comparison:
    same: bool
    how: str                         # code, includes, or exact for a kind with no rules for the mode
    before_line: int                 # the first line that differs, from 1, or 0 where the text has ended
    after_line: int
    added: tuple[str, ...] = ()      # include lines the after text has and the before text lacks
    removed: tuple[str, ...] = ()


MODES = ("code", "includes", "exact")


def first_mismatch(before: list[str], after: list[str]) -> int | None:
    """The first index where the two lists differ, counting a list that ends early, or None."""
    at = next((index for index, (one, other) in enumerate(zip(before, after)) if one != other), None)
    if at is None and len(before) != len(after):
        return min(len(before), len(after))
    return at


def compare(before: str, after: str, suffix: str, mode: str) -> Comparison:
    """Whether after holds the same code as before, as mode reads it: code without comments and layout,
    lines without includes and their order, or the exact lines. A kind with no rules for mode compares
    exactly, and the result says so."""
    if mode == "code" and (old := code_tokens(before, suffix)) is not None:
        new = code_tokens(after, suffix)
        at = first_mismatch([token.text for token in old], [token.text for token in new])
        if at is None:
            return Comparison(True, "code", 0, 0)
        lines = (tokens[at].line if at < len(tokens) else 0 for tokens in (old, new))
        return Comparison(False, "code", *lines)
    if mode == "includes" and (old_split := split_includes(before, suffix)) is not None:
        new_split = split_includes(after, suffix)
        at = first_mismatch([text for _, text in old_split[1]], [text for _, text in new_split[1]])
        added = tuple(sorted(set(new_split[0]) - set(old_split[0])))
        removed = tuple(sorted(set(old_split[0]) - set(new_split[0])))
        lines = (0, 0) if at is None else tuple(rest[at][0] if at < len(rest) else 0
                                                for rest in (old_split[1], new_split[1]))
        return Comparison(at is None and not added and not removed, "includes", *lines, added, removed)
    old_lines, new_lines = before.splitlines(keepends=True), after.splitlines(keepends=True)
    at = first_mismatch(old_lines, new_lines)
    if at is None:
        return Comparison(True, "exact", 0, 0)
    return Comparison(False, "exact", *(at + 1 if at < len(lines) else 0 for lines in (old_lines, new_lines)))


def split_includes(text: str, suffix: str) -> tuple[list[str], list[tuple[int, str]]] | None:
    """The include lines of text, stripped, and every other line with its number and its trailing whitespace
    gone, or None when io-guard knows no include form for suffix."""
    pattern = INCLUDE.get(suffix.lower())
    if pattern is None:
        return None
    includes, rest = [], []
    for number, line in enumerate(text.removeprefix(BOM_CHAR).splitlines(), 1):
        if pattern.match(line):
            includes.append(line.strip())
        else:
            rest.append((number, line.rstrip()))
    return includes, rest
