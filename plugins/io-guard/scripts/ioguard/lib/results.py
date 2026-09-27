"""The codes io-guard reports and the one shape every result takes.

CODES is the one declaration. The Code enum, the skill's code table, the telemetry vocabulary and the meta
test that demands a producing test per code all read it. A code is append-only: its name and meaning never
change. Each check appends its codes in the task that builds it. docs/design/architecture.md, section 2,
lists the codes the plan settled on.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any


class Severity(Enum):
    FIXED = "fixed"          # the call ran after a mechanical fix
    WARNING = "warning"      # the call ran, and context was added
    REFUSED = "refused"      # the call did not run
    INFO = "info"            # a fact, such as a profile line


class Layer(IntEnum):
    LOCATION = 1
    TRANSPORT = 2
    BYTES = 3
    STALE = 4
    READ = 5
    OUTPUT = 6
    INTERNAL = 7


@dataclass(frozen=True)
class CodeSpec:
    code: str
    layer: Layer
    severity: Severity
    summary: str             # one sentence, present tense: what happened
    fix: str                 # one sentence: what to do, naming the tool
    since: str               # the plugin version that introduced it


CODES: tuple[CodeSpec, ...] = (
    CodeSpec("GUARD_ERROR", Layer.INTERNAL, Severity.WARNING,
             "An io-guard check failed on this call, so io-guard skipped that check and let the call go on.",
             "Nothing to do, because the debug log holds the details.", "0.1"),
    CodeSpec("REWRITE_CONFLICT", Layer.INTERNAL, Severity.WARNING,
             "Two io-guard fixes changed the same part of this call, so io-guard kept the first and "
             "dropped the second.", "Nothing to do, because the first fix applied.", "0.1"),
    CodeSpec("BUDGET_EXCEEDED", Layer.INTERNAL, Severity.WARNING,
             "io-guard ran out of time on this call and skipped its remaining checks.",
             "Nothing to do, because the call went ahead without those checks.", "0.1"),
    CodeSpec("LINKED_PATH", Layer.LOCATION, Severity.WARNING,
             "The path runs through a junction or symbolic link into another repository.",
             "Change the file in the repository that owns it, unless the task is about that repository.",
             "0.1"),
    CodeSpec("READ_ONLY", Layer.LOCATION, Severity.REFUSED,
             "The file is read-only, so the write would fail or stop the session at a prompt.",
             "Ask the user to make it writable, such as by checking it out in their version control.", "0.1"),
    CodeSpec("FILE_LOCKED", Layer.LOCATION, Severity.WARNING,
             "Another process holds the file open, so the tool could not replace it.",
             "Close that program or wait for it, then call the same tool again, never a shell write.", "0.1"),
    CodeSpec("ANCHOR_NOT_FOUND", Layer.STALE, Severity.WARNING,
             "The Edit's old_string is not in the file, so the Edit was refused.",
             "Call Edit again with old_string copied from the lines the message shows.", "0.1"),
    CodeSpec("ANCHOR_AMBIGUOUS", Layer.STALE, Severity.WARNING,
             "The Edit's old_string is in the file more than once, so the Edit was refused.",
             "Call Edit again with a longer old_string that names one place, or with replace_all set.",
             "0.1"),
    CodeSpec("STALE_VIEW", Layer.STALE, Severity.WARNING,
             "The file holds something other than what the call expected.",
             "Read the file again, then change only what differs.", "0.1"),
    CodeSpec("PATH_NOT_FOUND", Layer.READ, Severity.WARNING,
             "The path does not exist.",
             "Call the tool again with one of the paths the message names.", "0.1"),
    CodeSpec("READ_TOO_LARGE", Layer.READ, Severity.WARNING,
             "The file is larger than one Read returns.",
             "Read it in the parts the message names, with offset and limit.", "0.1"),
    CodeSpec("PATTERN_INVALID", Layer.READ, Severity.WARNING,
             "ripgrep rejected the Grep pattern before it searched.",
             "Call Grep again with the pattern the message gives.", "0.1"),
    CodeSpec("SEARCH_TOO_BROAD", Layer.READ, Severity.WARNING,
             "The search ran out of time before it finished.",
             "Search a narrower folder, or add a glob or type filter.", "0.1"),
    CodeSpec("BODY_MOVED_TO_FILE", Layer.TRANSPORT, Severity.FIXED,
             "The command's body was written to a file, and the command reads that file.",
             "Nothing to do.", "0.1"),
    CodeSpec("TRANSPORT_BUDGET", Layer.TRANSPORT, Severity.REFUSED,
             "The command is longer than the Bash tool carries on this platform.",
             "Write the script to a file with the Write tool, then run the file.", "0.1"),
    CodeSpec("SHELL_WRITE", Layer.TRANSPORT, Severity.REFUSED,
             "The command writes a file git tracks through the shell, around io-guard's checks.",
             "Use the Edit tool to change the file, or the Write tool to replace it whole.", "0.1"),
    CodeSpec("BACKSLASH_TRANSPORT", Layer.TRANSPORT, Severity.WARNING,
             "The Bash tool on Windows halves a pair of backslashes in this command.",
             "If the command needs both, put the text in a file with the Write tool and read it from there.",
             "0.1"),
    CodeSpec("BACKTICK_IN_DOUBLE_QUOTES", Layer.TRANSPORT, Severity.REFUSED,
             "Bash runs the text between backticks inside double quotes as a command.",
             "Put that text in single quotes, or escape each backtick with a backslash.", "0.1"),
    CodeSpec("TRAILING_BACKSLASH_QUOTE", Layer.TRANSPORT, Severity.FIXED,
             "A backslash before a closing double quote escapes the quote in bash, so io-guard wrote the "
             "path with forward slashes.", "Nothing to do.", "0.1"),
    CodeSpec("DIALECT_MISMATCH", Layer.TRANSPORT, Severity.REFUSED,
             "The command is written for the other shell.",
             "Send it to the tool for that shell, or write it for this one.", "0.1"),
    CodeSpec("POWERSHELL_TRAP", Layer.TRANSPORT, Severity.REFUSED,
             "PowerShell refuses this command before it does anything.",
             "Change the command as the message says, then run it again.", "0.1"),
    CodeSpec("PIPE_HIDES_EXIT", Layer.TRANSPORT, Severity.WARNING,
             "A pipe gives the command the exit code of its last part, which hides a build or test failure.",
             "Read the output for the result, not the exit code.", "0.1"),
    CodeSpec("INLINE_SCRIPT_INVALID", Layer.TRANSPORT, Severity.REFUSED,
             "The Python program in this command does not compile.",
             "Fix the line the message names, then run the command again.", "0.1"),
    CodeSpec("MSYS_PATH", Layer.TRANSPORT, Severity.FIXED,
             "Git Bash would turn an argument that starts with a slash into a path under its install "
             "folder, so io-guard kept it as written.", "Nothing to do.", "0.1"),
    CodeSpec("RESERVED_NAME", Layer.TRANSPORT, Severity.REFUSED,
             "The path is a Windows device name, such as nul or con, which Windows tools cannot open or "
             "delete as a file.", "Use /dev/null in Bash, or another name for a file.", "0.1"),
    CodeSpec("EOL_CONVERTED", Layer.BYTES, Severity.FIXED,
             "io-guard wrote the new text in the file's own line endings.", "Nothing to do.", "0.1"),
    CodeSpec("BOM_RESTORED", Layer.BYTES, Severity.FIXED,
             "io-guard kept the file's byte order mark, which the Write tool drops.", "Nothing to do.",
             "0.1"),
    CodeSpec("EOL_MISMATCH", Layer.BYTES, Severity.WARNING,
             "The new text's line endings differ from the file's.",
             "Write the whole file in one ending.", "0.1"),
    CodeSpec("INDENT_MISMATCH", Layer.BYTES, Severity.FIXED,
             "The new text's indent differs from the lines around it, tabs against spaces.",
             "Indent the new text as the lines around it are.", "0.1"),
    CodeSpec("BOM_CHANGED", Layer.BYTES, Severity.WARNING,
             "The write added or removed the file's byte order mark.",
             "Write the file again with its BOM as it was.", "0.1"),
    CodeSpec("ENCODING_INVALID", Layer.BYTES, Severity.WARNING,
             "The write left bytes that are not UTF-8, or U+FFFD characters where others could not be read.",
             "Read the lines the message names, and put back the characters they lost.", "0.1"),
    CodeSpec("CONTROL_BYTES_ADDED", Layer.BYTES, Severity.WARNING,
             "The write added NUL or other control bytes to a text file.",
             "Remove them with the Edit tool, on the lines the message names.", "0.1"),
    CodeSpec("NON_ASCII_ADDED", Layer.BYTES, Severity.WARNING,
             "The write added non-ASCII characters to a file this project keeps ASCII.",
             "Replace them with ASCII, on the lines the message names.", "0.1"),
    CodeSpec("SIZE_COLLAPSED", Layer.BYTES, Severity.WARNING,
             "The file holds far fewer bytes than the call should have left in it.",
             "Read the file, and write the missing text back.", "0.1"),
    CodeSpec("UNINTENDED_CHANGE", Layer.BYTES, Severity.WARNING,
             "Lines changed that the call did not ask to change.",
             "Read the lines the message names, and put back any change the call did not make.", "0.1"),
)
Code = Enum("Code", {spec.code: spec.code for spec in CODES})
SPECS: dict[Code, CodeSpec] = {Code[spec.code]: spec for spec in CODES}


@dataclass(frozen=True)
class Fix:
    tool: str                                # "Edit", "Write", "Bash", or a callable MCP name
    input: Mapping[str, Any]
    text: str                                # the second sentence of the message: what to do


@dataclass(frozen=True)
class Result:
    code: Code
    severity: Severity
    message: str                             # the first sentence: what happened
    tool: str
    platform: str
    file: Path | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    fix: Fix | None = None
    auto_fixed: tuple[Code, ...] = ()

    @classmethod
    def of(cls, code: Code, message: str, tool: str, platform: str, **fields: Any) -> "Result":
        """A result with the severity its code declares, unless fields names another."""
        severity = fields.pop("severity", SPECS[code].severity)
        return cls(code=code, severity=severity, message=message, tool=tool, platform=platform, **fields)

    def render(self) -> str:
        return render(self)

    def to_json(self) -> dict:
        return {
            "ok": self.severity is not Severity.REFUSED,
            "code": self.code.value,
            "severity": self.severity.value,
            "tool": self.tool,
            "platform": self.platform,
            "file": None if self.file is None else self.file.as_posix(),
            "message": self.message,
            "evidence": dict(self.evidence),
            "fix": None if self.fix is None else {"tool": self.fix.tool, "input": dict(self.fix.input)},
            "auto_fixed": [code.value for code in self.auto_fixed],
        }


def spec(code: Code) -> CodeSpec:
    return SPECS[code]


def render(result: Result) -> str:
    """CODE: what happened. What to do. The second sentence is the fix's text, or the code's general fix. A
    message that ends in quoted lines of a file puts the fix on a line of its own."""
    advice = result.fix.text if result.fix is not None else SPECS[result.code].fix
    separator = "\n" if "\n" in result.message else " "
    return f"{result.code.value}: {result.message}{separator}{advice}"


def render_many(results: Sequence[Result]) -> str:
    return "\n".join(render(result) for result in results)
