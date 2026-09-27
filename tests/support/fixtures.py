"""The byte fixtures in tests/fixtures/, and MANIFEST.sha256, which holds the hash of every fixture file.

    python -m tests.support.fixtures

rewrites each generated fixture and the manifest. The hook events in tests/fixtures/events/ were recorded by
task 03's probes and are hashed as they are. .gitattributes marks the folder -text, and test_meta compares
every file against the manifest, so a fixture git converted fails the suite.
"""
import hashlib
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
MANIFEST = FIXTURES_DIR / "MANIFEST.sha256"
BOM = b"\xef\xbb\xbf"
LARGE_BYTES = 300 * 1024


def large_text() -> bytes:
    """LF lines, numbered, until the text reaches 300 KB."""
    lines, size, number = [], 0, 1
    while size < LARGE_BYTES:
        line = f"line {number:06d} of the 300 KB fixture\n".encode("ascii")
        lines.append(line)
        size += len(line)
        number += 1
    return b"".join(lines)


GENERATED = {
    "crlf.txt": b"one\r\ntwo\r\nthree\r\n",
    "lf.txt": b"one\ntwo\nthree\n",
    "mixed.txt": b"one\r\ntwo\nthree\r\nfour\n",
    "lone-cr.txt": b"one\r\ntwo\rthree\r\n",
    "bom-crlf.txt": BOM + b"one\r\ntwo\r\n",
    "bom-lf.txt": BOM + b"one\ntwo\n",
    "cp1250.txt": b"za\xbf\xf3\xb3\xe6 g\xea\x9cl\xb9 ja\x9f\xf1\r\n",
    "private-use.txt": b"branch \xee\x82\xa0 main\n",
    "nul-byte.txt": b"before\x00after\n",
    "indent-tab.cpp": b"void f()\n{\n\tint x = 1;\n\treturn;\n}\n",
    "indent-space.cpp": b"void f()\n{\n    int x = 1;\n    return;\n}\n",
    "indent-both.cpp": b"void f()\n{\n\tint x = 1;\n    return;\n}\n",
    "no-final-newline.txt": b"one\ntwo",
    "empty.txt": b"",
    "large-300k.txt": large_text(),
}


def fixture_files() -> list[Path]:
    """Every fixture file, the manifest excepted, in a stable order."""
    return sorted(path for path in FIXTURES_DIR.rglob("*") if path.is_file() and path != MANIFEST)


def manifest_name(path: Path) -> str:
    return path.relative_to(FIXTURES_DIR).as_posix()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest() -> dict[str, str]:
    """The manifest as {name: sha256}, from lines in sha256sum's format."""
    entries = {}
    for line in MANIFEST.read_bytes().decode("ascii").splitlines():
        hash_hex, name = line.split("  ", 1)
        entries[name] = hash_hex
    return entries


def rewrite() -> None:
    for name, data in GENERATED.items():
        (FIXTURES_DIR / name).write_bytes(data)
    lines = [f"{digest(path)}  {manifest_name(path)}\n" for path in fixture_files()]
    MANIFEST.write_bytes("".join(lines).encode("ascii"))


if __name__ == "__main__":
    rewrite()
    print(f"wrote {len(GENERATED)} fixtures and a manifest of {len(fixture_files())} files")
