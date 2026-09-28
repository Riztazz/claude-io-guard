"""The io-guard skill page: hand-written steps, and two tables generated from the one declaration of each, the
tool table from the io server's registry and the code table from CODES.

A line before and a line after each table mark it, and written puts the table the declarations give between
them. A test compares the shipped page with that, so a new tool or code cannot ship without its row. The
tables come from here rather than cli, because the tool table needs the registry, and cli never imports mcp.
"""
from collections.abc import Mapping, Sequence
from pathlib import Path

from ioguard.lib.bytesio import read_bytes, write_atomic
from ioguard.lib.results import CODES, CodeSpec
from ioguard.mcp.server import registry

PAGE = Path(__file__).resolve().parents[3] / "skills" / "io-guard" / "SKILL.md"
SOURCES = {"tools": "the io server's tool list", "codes": "io-guard's code list"}


def begin(name: str) -> str:
    return f"<!-- Generated from {SOURCES[name]}. An edit between here and the end line is overwritten. -->"


def end(name: str) -> str:
    return f"<!-- The generated {name} table ends here. -->"


def cell(text: str) -> str:
    return text.replace("|", "\\|")


def code_table(codes: Sequence[CodeSpec] = CODES) -> str:
    """Each code, what happened and what to do, by name."""
    rows = [f"| `{spec.code}` | {cell(spec.summary)} | {cell(spec.fix)} |"
            for spec in sorted(codes, key=lambda spec: spec.code)]
    return "\n".join(["| Code | What happened | What to do |", "|---|---|---|", *rows])


def tables() -> dict[str, str]:
    return {"tools": registry().markdown(), "codes": code_table()}


def written(page: str, generated: Mapping[str, str]) -> str:
    """page with each generated table between its two lines. ValueError names a table whose lines are
    missing or out of order."""
    for name, table in generated.items():
        first, last = begin(name), end(name)
        start, stop = page.find(first), page.find(last)
        if start < 0 or stop < start:
            raise ValueError(f"The skill page has no '{first}' line followed by '{last}'.")
        page = page[:start + len(first)] + "\n" + table + "\n" + page[stop:]
    return page


def main(argv: Sequence[str]) -> int:
    """Write the tables into the page, or with --check exit 1 when the page's tables are out of date."""
    page = read_bytes(PAGE).decode("utf-8")
    fresh = written(page, tables())
    if "--check" in argv:
        if fresh != page:
            print(f"{PAGE} is out of date. Run python tools/skill.py to write its tables.")
            return 1
        return 0
    if fresh != page:
        write_atomic(PAGE, fresh.encode("utf-8"))
        print(f"Wrote the tables into {PAGE}.")
    return 0
