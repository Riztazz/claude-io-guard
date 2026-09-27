"""Tell the agent a file's endings, BOM, encoding and indent after it reads the file.

The Read tool shows a CRLF file, an LF file and a file with a BOM the same way (BYT-4), so the agent cannot
see the convention a write has to keep. After each Read the check profiles the file's bytes on disk and adds
one line, such as io-guard: CRLF, BOM, UTF-8, tabs, 1,284 lines, and one more when the bytes hold a hazard.
It keeps the hash of the whole file in the session, also after a Read of a few lines, for the checks that
compare a later write with what the agent saw. A binary file, such as an image the Read tool shows as a
picture, gets its hash and no line. A file past max_bytes gets neither, because the check would profile only
the part of it that fits.
"""
from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.profile import profile
from ioguard.lib.results import Layer, Severity

MAX_BYTES = 16 * 1024 * 1024


class ReadProfile(Check):
    meta = CheckMeta(
        id="read.profile", layer=Layer.READ, events=frozenset({HookEvent.POST_TOOL_USE}),
        tools=frozenset({Tool.READ}), platforms=frozenset({"win32", "darwin"}), severity=Severity.INFO,
        cost=Cost.MEDIUM, reads=frozenset({"file_path"}), writes=frozenset(), after=frozenset(),
        config={"max_bytes": ConfigKey(int, MAX_BYTES, "The largest file, in bytes, that gets a profile line "
                                       "after a Read. A larger one gets none.")},
        codes=frozenset(),
        description="Adds the file's endings, BOM, encoding and indent after each Read.")

    def run(self, event: Event, ctx: Context) -> Decision:
        if event.file_path is None:
            return Decision.observe(self.meta.id)
        limit = self.options["max_bytes"]
        try:
            data = ctx.fs.read_bytes(event.file_path, limit + 1)
        except OSError:
            return Decision.observe(self.meta.id)
        if len(data) > limit:
            return Decision.observe(self.meta.id)
        found = profile(data)
        with ctx.session.lock:
            ctx.session.read_hashes[event.file_path] = found.sha256
        if found.binary:
            return Decision.observe(self.meta.id)
        lines = [f"io-guard: {found.line()}"]
        if found.warnings():
            lines.append("io-guard: " + " ".join(found.warnings()))
        return Decision(self.meta.id, Verdict.ALLOW, context=tuple(lines))
