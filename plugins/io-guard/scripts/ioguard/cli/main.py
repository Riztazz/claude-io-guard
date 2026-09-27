"""The ioguard command line. Each command parses its arguments and calls the cli module that does the work.

    corpus NAME=FOLDER [NAME=FOLDER ...] [--out corpus]
    replay [--corpus corpus] [--project NAME ...] [--out FILE]
    precommit
"""
import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from ioguard.checks.registry import default_registry
from ioguard.cli import corpus, precommit, replay


def source(text: str) -> tuple[str, Path]:
    name, found, folder = text.partition("=")
    if not found or not name or not folder:
        raise argparse.ArgumentTypeError(
            f"{text!r} is not NAME=FOLDER, such as myproject=<transcript folder>")
    path = Path(folder).expanduser()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"{path} is not a folder of transcripts")
    return name, path


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="ioguard")
    commands = top.add_subparsers(dest="command", required=True)
    build = commands.add_parser("corpus", help="build the replay corpus from transcript folders")
    build.add_argument("sources", nargs="+", type=source, metavar="NAME=FOLDER")
    build.add_argument("--out", type=Path, default=Path("corpus"))
    run = commands.add_parser("replay", help="replay the corpus through every check, offline")
    run.add_argument("--corpus", type=Path, default=Path("corpus"))
    run.add_argument("--project", action="append", default=[], help="replay only this project, repeatable")
    run.add_argument("--out", type=Path, help="the JSON report, reports/replay-<time>.json by default")
    commands.add_parser("precommit", help="check the staged files' bytes against their last commit, exit 1 "
                                          "on a finding")
    return top


def main(argv: Sequence[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")    # a cp1252 console cannot print every sample
    args = parser().parse_args(argv)
    match args.command:
        case "corpus":
            index = corpus.build(args.sources, args.out)
            counts = {name: sum(tools.values()) for name, tools in index["records"].items()}
            print(f"Wrote {sum(counts.values())} records to {args.out}: {counts}. "
                  f"{index['copies']} copies of a call already written were skipped, "
                  f"{index['unpaired']} calls had no result, and {index['unreadable']} lines were not JSON.")
        case "replay":
            if not (args.corpus / "index.json").is_file():
                print(f"{args.corpus} holds no corpus. Build one with the corpus command first.")
                return 1
            report = replay.replay(corpus.load(args.corpus, args.project), default_registry(), args.corpus)
            out = args.out or Path("reports") / f"replay-{time.strftime('%Y%m%d-%H%M%S')}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes((json.dumps(report, indent=1, ensure_ascii=True) + "\n").encode("ascii"))
            print(replay.render(report))
            print(f"The full report is {out}.")
        case "precommit":
            code, text = precommit.run(Path.cwd(), os.environ)
            if text:
                print(text)
            return code
    return 0
