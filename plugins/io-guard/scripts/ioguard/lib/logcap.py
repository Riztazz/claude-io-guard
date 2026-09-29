"""Copy a background run's output into its log, up to a cap, and drop the rest.

usage: python logcap.py <log> <max bytes>

The run writes into this program's stdin, and this program runs as its own process, so the cap holds after
the io server that started the run has ended, as the run itself goes on (architecture.md, section 8). Past
the cap it writes one line that says the log stopped, then reads and drops the rest, so the run never blocks
on a full pipe. It exits when the run closes its output. Standard library only, since it runs by its path.
"""
import sys
from typing import BinaryIO

CUT = b"\n[io-guard: the log stopped here at its size cap, and the run went on]\n"
BLOCK = 64 * 1024


def copy(source: BinaryIO, target: BinaryIO, cap: int) -> bool:
    """source into target up to cap bytes, then CUT once. Whether the output went past the cap."""
    written, cut = 0, False
    read = getattr(source, "read1", source.read)
    while block := read(BLOCK):
        if written >= cap:
            continue
        kept = block[:cap - written]
        target.write(kept)
        written += len(kept)
        if len(kept) < len(block):
            target.write(CUT)
            cut = True
        target.flush()
    return cut


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1:2] == ["--help"]:
        print(__doc__.strip())
        return 0 if argv[1:2] == ["--help"] else 2
    with open(argv[1], "ab") as target:
        copy(sys.stdin.buffer, target, int(argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
