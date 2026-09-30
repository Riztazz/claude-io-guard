"""The ioguard command line. Each command parses its arguments and calls the cli module that does the work.

    corpus NAME=FOLDER [NAME=FOLDER ...] [--out corpus]
    replay [--corpus corpus] [--project NAME ...] [--out FILE]
    precommit
    report [--data FOLDER ...] [--days 7] [--html FILE]
    measure NAME=FOLDER [NAME=FOLDER ...] [--since YYYY-MM-DD] [--data FOLDER ...]
    check COMMAND [--tool Bash|PowerShell] [--cwd FOLDER]
    profile FILE [FILE ...]
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from ioguard.checks.registry import default_registry
from ioguard.cli import check, corpus, measure, precommit, replay, report
from ioguard.lib import telemetry_summary
from ioguard.lib.decisions import Verdict
from ioguard.lib.folders import home_folder


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
    week = commands.add_parser("report", help="what io-guard fixed, warned about and refused, from telemetry")
    week.add_argument("--data", type=Path, action="append", default=[],
                      help="a folder io-guard wrote telemetry to, repeatable, io-guard's own by default")
    week.add_argument("--days", type=int, default=7, help="the days to report, counting back from now")
    week.add_argument("--html", type=Path, help="write the dashboard page's stats to this file instead")
    rate = commands.add_parser("measure", help="the baseline's failure classes before and after io-guard")
    rate.add_argument("sources", nargs="+", type=source, metavar="NAME=FOLDER")
    rate.add_argument("--since", type=measure.since_date, default=measure.ADOPTED,
                      help="the first day with io-guard on, YYYY-MM-DD")
    rate.add_argument("--data", type=Path, action="append", default=[],
                      help="a folder io-guard wrote telemetry to, for the guard's own time, io-guard's "
                           "own by default")
    one = commands.add_parser("check", help="what every check decides about one command, which never runs, "
                                            "exit 1 on a refusal")
    one.add_argument("shell_command", metavar="COMMAND")
    one.add_argument("--tool", choices=["Bash", "PowerShell"], default="Bash")
    one.add_argument("--cwd", type=Path, default=Path.cwd(),
                     help="the folder it runs from, this one by default")
    shape = commands.add_parser("profile", help="the profile line a Read of each file gets")
    shape.add_argument("files", nargs="+", type=Path, metavar="FILE")
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
            replayed = replay.replay(corpus.load(args.corpus, args.project), default_registry(), args.corpus)
            out = args.out or Path("reports") / f"replay-{time.strftime('%Y%m%d-%H%M%S')}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes((json.dumps(replayed, indent=1, ensure_ascii=True) + "\n").encode("ascii"))
            print(replay.render(replayed))
            print(f"The full report is {out}.")
        case "precommit":
            code, text = precommit.run(Path.cwd(), os.environ)
            if text:
                print(text)
            return code
        case "report":
            folders = args.data or [home_folder(os.environ)]
            missing = [folder for folder in folders if not folder.is_dir()]
            if missing:
                print(f"io-guard has no folder at {missing[0]}. Name the folder with --data.")
                return 1
            if args.html is not None:
                args.html.write_bytes(report.static_page(folders, args.days, datetime.now(timezone.utc)))
                print(f"Wrote the last {args.days} days to {args.html}, which opens in any browser.")
            else:
                print(report.run(folders, args.days, datetime.now(timezone.utc)))
        case "measure":
            before, after = measure.measure(corpus.records(args.sources, corpus.Tally(Counter(), Counter())),
                                            args.since)
            since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            folders = args.data or [home_folder(os.environ)]
            telemetry = telemetry_summary.summarise(telemetry_summary.files(folders, since), since)
            print(measure.render(before, after, telemetry_summary.spread(telemetry.hook_ms).get("p95")))
        case "check":
            if not args.cwd.is_dir():
                print(f"{args.cwd} is not a folder. Name the folder the command runs from with --cwd.")
                return 1
            outcome = check.check(args.shell_command, args.cwd.resolve(), os.environ, args.tool)
            print(check.render(outcome))
            return 1 if outcome.verdict is Verdict.DENY else 0
        case "profile":
            missing = [path for path in args.files if not path.is_file()]
            if missing:
                print(f"{missing[0]} is not a file.")
                return 1
            print("\n".join(check.profiled(path) for path in args.files))
    return 0
