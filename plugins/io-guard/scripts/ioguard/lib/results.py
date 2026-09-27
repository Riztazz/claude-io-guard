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
    CodeSpec("BODY_MOVED_TO_FILE", Layer.TRANSPORT, Severity.FIXED,
             "The command's body was written to a file, and the command reads that file.",
             "Nothing to do.", "0.1"),
    CodeSpec("TRANSPORT_BUDGET", Layer.TRANSPORT, Severity.REFUSED,
             "The command is longer than the Bash tool carries on this platform.",
             "Write the script to a file with the Write tool, then run the file.", "0.1"),
    CodeSpec("BACKSLASH_TRANSPORT", Layer.TRANSPORT, Severity.WARNING,
             "The Bash tool on Windows halves a pair of backslashes in this command.",
             "If the command needs both, put the text in a file with the Write tool and read it from there.",
             "0.1"),
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
    """CODE: what happened. What to do. The second sentence is the fix's text, or the code's general fix."""
    advice = result.fix.text if result.fix is not None else SPECS[result.code].fix
    return f"{result.code.value}: {result.message} {advice}"


def render_many(results: Sequence[Result]) -> str:
    return "\n".join(render(result) for result in results)
