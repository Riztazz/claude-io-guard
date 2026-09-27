"""Compiling a Python program's text without running it, to find what stops it before it starts.

compile() raises a SyntaxError, and reports a SyntaxWarning, such as an invalid escape sequence, through the
warnings module, whose filters every thread shares. One lock keeps a single compile at a time inside the
filters it sets, and only warnings raised for this module's own file name count.
"""
import threading
import warnings
from dataclasses import dataclass

NAME = "<io-guard body>"
LOCK = threading.Lock()


@dataclass(frozen=True)
class Problem:
    message: str
    line: int | None
    text: str                    # that line as written, stripped


@dataclass(frozen=True)
class CompileReport:
    error: Problem | None
    warnings: tuple[Problem, ...]


def compile_report(source: str) -> CompileReport | None:
    """What compiling source reports. None when the compiler itself gives out, on nesting too deep for it."""
    lines = source.splitlines()

    def problem(message: str, line: int | None) -> Problem:
        text = lines[line - 1].strip() if line and 0 < line <= len(lines) else ""
        return Problem(message, line, text)

    with LOCK, warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SyntaxWarning)
        try:
            compile(source, NAME, "exec", dont_inherit=True)
        except SyntaxError as error:
            return CompileReport(problem(error.msg, error.lineno), ())
        except (RecursionError, MemoryError):
            return None
    return CompileReport(None, tuple(problem(str(item.message), item.lineno) for item in caught
                                     if issubclass(item.category, SyntaxWarning) and item.filename == NAME))
