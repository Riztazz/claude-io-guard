"""Probe files for the Edit and Write tools' byte behaviour, in this scratchpad only.

    python eol_probe.py make     writes eol_crlf.txt (CRLF), eol_lf.txt (LF) and eol_bom.txt (CRLF with a BOM)
    python eol_probe.py show     prints each file's bytes, ending counts and BOM
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {
    "eol_crlf.txt": b"one\r\ntwo\r\nthree\r\n",
    "eol_lf.txt": b"one\ntwo\nthree\n",
    "eol_bom.txt": b"\xef\xbb\xbfone\r\ntwo\r\nthree\r\n",
}

if sys.argv[1] == "make":
    for name, data in FILES.items():
        with open(os.path.join(HERE, name), "wb") as handle:
            handle.write(data)
    print("made", ", ".join(FILES))
else:
    for name in FILES:
        data = open(os.path.join(HERE, name), "rb").read()
        crlf = data.count(b"\r\n")
        lf = data.count(b"\n") - crlf
        print("%-13s bom=%s crlf=%d lf=%d bytes=%r" % (name, data.startswith(b"\xef\xbb\xbf"), crlf, lf, data))
