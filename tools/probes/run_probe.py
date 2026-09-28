"""Build a one-off plugin per probe, run a headless Claude Code session with it, and collect what happened.

    python tools/probes/run_probe.py list
    python tools/probes/run_probe.py run <id> [<id> ...] | all
    python tools/probes/run_probe.py brief <id> [<id> ...]
    python tools/probes/run_probe.py timing <id> [<id> ...]
    python tools/probes/run_probe.py verdicts [<id> ...]
    python tools/probes/run_probe.py show <id>
    python tools/probes/run_probe.py assemble <id> <folder>

A run writes to workbench/probes/<id>/<time>/: the plugin it loaded, the work folder the session ran in, the
session's stream-json output, the debug log, the hook and server log, and summary.json. workbench/ is
gitignored, because the logs hold local paths. brief, timing, verdicts and show read the latest run of a
probe. verdicts prints pass or FAIL per probe against the result context.md records. run all runs every probe
that has a verdict. The launch probes, which time 100 hook calls each for docs/launcher.md, run by name.
assemble builds the plugin alone, wrapped in a local marketplace, for a probe a person runs by hand in the
desktop app. IOPROBE_CLAUDE names the claude binary to run, for example the desktop app's bundled copy, and
defaults to claude on PATH. context.md, "Hooks and MCP", records what each probe found.

A live-* probe runs io-guard itself from plugins/io-guard instead of a one-off plugin, with IOGUARD_PYTHON
naming this Python and tests/support/inject on PYTHONPATH, so the test checks its guard field names run in the
hook and the server as shipped. Its log is the session's io-guard telemetry. The guard-* probes point the
one-off plugin's hooks at io-guard's own hooks.json maps, to record what they receive.
"""
import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "workbench" / "probes"
PYTHON = Path(sys.executable)
SERVER = "plugin:io-probe:probe"
MCP = "mcp__plugin_io-probe_probe__"
GATE_INPUT = {
    "hook_event_name": "${hook_event_name}", "tool_name": "${tool_name}",
    "command": "${tool_input.command}", "number": "${tool_input.timeout}",
    "boolean": "${tool_input.run_in_background}", "replace_all": "${tool_input.replace_all}",
    "content": "${tool_input.content}", "object": "${tool_input}", "absent": "${tool_input.io_probe_absent}",
    "literal_number": 7, "literal_bool": True,
}
PERMIT = ("--permission-prompts", "host", "--permission-prompt-tool", MCP + "probe_permit")
RAN = "Run this exact Bash command: echo IOPROBE_RAN > ran.txt\nThen quote word for word any hook message " \
      "or error you saw."
TWO_RUNS = "Run these two Bash commands one at a time, each in its own tool call: echo IOPROBE_FIRST > " \
           "first.txt and then echo IOPROBE_SECOND > second.txt\nThen quote word for word any hook message " \
           "or error you saw."
TEN_ECHOES = "Run these ten Bash commands one at a time, each in its own Bash tool call, in order: " + \
             ", ".join(f"echo n{n}" for n in range(1, 11)) + ". Then reply DONE."
HUNDRED_ECHOES = "Run the Bash command echo n1, then echo n2, and so on up to echo n100: one hundred " \
                 "commands, one at a time, each in its own Bash tool call, never two in one message. Then " \
                 "reply DONE."
GUARD = REPO / "plugins" / "io-guard"
GUARD_HOME = REPO / "workbench" / "io-guard-home"
NEEDS_AUTH = Path.home() / ".claude" / "mcp-needs-auth-cache.json"
GUARD_INPUTS = {event: groups[0]["hooks"][0].get("input") for event, groups in
                json.loads((GUARD / "hooks" / "hooks.json").read_bytes())["hooks"].items()}
INJECT = REPO / "tests" / "support" / "inject"
PYRUN = (GUARD / "scripts" / "pyrun").as_posix()
HOOK_PY = (GUARD / "scripts" / "hook.py").as_posix()
SED = "Read diff.txt. Then run this exact Bash command: sed -i 's/a/b/' diff.txt\nThen reply DONE."
THREE_FEATURES = "Call these three tools from the io-probe server once each, in order: probe_elicit, " \
                 "probe_progress, probe_app. Then quote each result word for word."
PLAIN_ONCE = "Call the probe_plain tool from the io-probe server once. Then reply DONE."
DESKTOP = "Run this exact Bash command: echo IOPROBE_ORIGINAL\nThen call these four tools from the " \
          "io-probe server once each, in order: probe_elicit, probe_progress, probe_app, probe_plain. " \
          "Then quote every result word for word."
AUTO = "This session is a harness test. ../outside is a scratch folder the test created for this step, and " \
       "deleting it is the point of the test. Run this exact Bash command and nothing else: rm -rf " \
       "../outside\nThen quote word for word what happened, including any refusal or permission message."
FAILURES = "Do these steps in order, one tool call each, and never retry a failed step. " \
           "1. Read missing.txt. 2. Run the Bash command: exit 3. 3. Read fail.txt. " \
           "4. Run the Bash command: echo changed >> fail.txt. 5. Use Edit on fail.txt to replace one " \
           "with ONE. 6. Use Edit on fail.txt to replace nine with NINE. Then, for each step, quote word " \
           "for word the error and any added note or context that came with its result."
SUBSTITUTION = "Do these in order, one tool call each. 1. Run the Bash command echo hi, with the Bash " \
               "tool's timeout parameter set to 60000 and run_in_background set to false. 2. Read s.txt. " \
               "3. Edit s.txt to replace one with ONE, with replace_all set to true. 4. Write w.txt with " \
               "exactly these three lines: say \"hi\" | C:\\temp\\new | zazolc with Polish letters: " + \
               b"za\xc5\xbc\xc3\xb3\xc5\x82\xc4\x87".decode("utf-8") + \
               " (put each part on its own line, without the | marks). Then reply DONE."
FIELDS = "Do these in order, one tool call each, and never retry a failed step. 1. Run the Bash command " \
         "echo hi. 2. Read s.txt. 3. Edit s.txt to replace one with ONE. 4. Write w.txt with two lines: " \
         "say \"hi\" and C:\\temp\\new. 5. Read missing.txt. 6. Run the Bash command: exit 3. " \
         "Then reply DONE."
LARGE = "Use the Write tool once to create big.txt. Its content is the line: The quick brown fox jumps " \
        "over the lazy dog, line NNNN. for each NNNN from 0001 to 2600, each on its own line, 2600 lines " \
        "in all. Write the whole file in that one Write call, and never shorten it. Then reply DONE."
LIVE = "Do these in order, one tool call each, and never retry a failed step. 1. Run the Bash command " \
       "echo hi. 2. Run the PowerShell command Write-Output hi. 3. Write w.txt with the line one. 4. Read " \
       "w.txt. 5. Edit w.txt to replace one with ONE. 6. Read missing.txt. Then quote word for word every " \
       "note or context that came with any tool result, and reply DONE."
ANSWERS = "Do these in order, one tool call each, and never retry. 1. Run the Bash command: echo " \
          "IOGUARD_ORIGINAL 2. Run the Bash command: echo IOGUARD_REFUSE 3. Read s.txt. Then quote word " \
          "for word each command's output, every refusal, and every note or context that came with any " \
          "tool result."
REFUSE_MODE = "Run this exact Bash command: echo IOGUARD_ORIGINAL\nIf it is refused, do what the refusal " \
              "says, once. Then quote word for word the refusal and the output."
MOVED = ("Run one Bash command: a python heredoc, written as python - <<'PY' on the first line, then 110 "
         "comment lines, each exactly: # io-guard transport check, padding line NNN of 110, carried to the "
         "file whole (with NNN from 001 to 110), then the line " + r'print(len(r"\\n"))' + " and then the "
         "line PY. Write every line out in full, in that one command. If the call is refused, do what the "
         "refusal says, once. Then reply with the number the command printed.")
READ_PROFILE = "Read profiled.txt with the Read tool. Then quote word for word any text that came with " \
               "that tool result besides the file's own lines, such as an added note or context. If there " \
               "was none, reply NONE."
CONFORM = "Do these in order, one tool call each, and never retry a failed step. 1. Read keep.txt. 2. Use " \
          "the Write tool on keep.txt with two lines: gamma and delta. Then reply DONE."
TRAILING = "Read one.txt, then use the Edit tool once on one.txt to replace one = 1 with one = 9. " \
           "Then reply DONE."
VERIFY = "Do these in order, one tool call each. 1. Read keep.txt. 2. Use the Write tool on keep.txt " \
         "with two lines: gamma and delta. 3. Read keep.txt again. 4. Use the Edit tool on keep.txt to " \
         "replace gamma with GAMMA. If a step fails, quote its error word for word and stop. Then reply DONE."
VERIFY_DIRECT = "Do these in order, one tool call each, and never read keep.txt a second time. 1. Read " \
                "keep.txt. 2. Use the Write tool on keep.txt with two lines: gamma and delta. 3. Use the " \
                "Edit tool on keep.txt to replace gamma with GAMMA. If a step fails, quote its error word " \
                "for word and stop. Then reply DONE."
EDIT_REFUSALS = ("Do these in order, one tool call each, and never retry a failed step. 1. Use the Edit "
                 "tool on unread.txt to replace alpha with beta, without reading it first. 2. Read f.txt. "
                 "3. Use the Edit tool on f.txt to replace nine with ten. 4. Use the Edit tool on f.txt to "
                 "replace x with y, with replace_all false. 5. Use the Edit tool on f.txt to replace one "
                 "with one. Then quote each tool's error word for word.")
OTHER_REFUSALS = ("Do these in order, one tool call each, and never retry a failed step. 1. Read big.txt "
                  "whole, with no offset or limit. 2. Grep for the pattern ( in this folder. 3. Grep for x "
                  "in the path missing-dir. 4. Glob for *.txt in the path missing-dir. 5. Use the Edit tool "
                  "on missing.txt to replace a with b. 6. Use the Write tool on kept.txt with the content x, "
                  "without reading it first. Then quote each tool's error word for word.")
DIAGNOSE = ("Do these in order, one tool call each, and never retry or fix a failed step. 1. Read "
            "a.cpp. 2. Use the Edit tool on a.cpp to replace the text '    int b = 2;' (four spaces "
            "first) with '    int b = 3;'. 3. Read a.cpp again. 4. Use the Edit tool on a.cpp to replace "
            "'int a = 1;' with 'int a = 9;'. 5. Read missing.txt. 6. Read big.txt whole, with no offset or "
            "limit. 7. Grep for the pattern f(x in this folder. 8. Use the Edit tool on a.cpp to replace "
            "'void f()' with 'void f()'. 9. Glob for *.txt in the path missing-dir. Then reply DONE.")
DIAGNOSE_CPP = b"void f()\r\n{\r\n\tint a = 1;\r\n\tint b = 2;\r\n\tint a = 1;\r\n}\r\n"
SPACE_DROPPED = ("Read ws.txt. Then use the Edit tool on ws.txt with replace_all true, with old_string "
                 "exactly '.Branch, ' and new_string exactly '.Branch.ToInt(), '. Each of the two strings "
                 "ends in one space, and the space is part of the string. If the Edit is refused, do what "
                 "the refusal says. Then reply DONE.")
SPACE_DROPPED_FILE = b"a = f(x.Branch, 1);\nb = f(y.Branch, 2);\n"
SPACE_KEPT = "a = f(x.Branch.ToInt(), 1);\nb = f(y.Branch.ToInt(), 2);\n"
DIAGNOSED = ("ANCHOR_NOT_FOUND: old_string of the refused Edit matches line 4 of a.cpp",
             "ANCHOR_AMBIGUOUS: ", "PATH_NOT_FOUND: missing.txt does not exist",
             "READ_TOO_LARGE: big.txt holds",
             "PATTERN_INVALID: ripgrep rejected the pattern", "PATH_NOT_FOUND: missing-dir does not exist")
TOUCHED = ("Do these in order, one tool call each, and never retry. 1. Read a.cpp. 2. Read conv.txt. 3. Run "
           "the Bash command: clang-format -i a.cpp 4. Run the Bash command: python conv.py Then reply DONE.")
TOUCHED_FILES = {"a.cpp": b"int   main( ){return 0;}\n", "conv.txt": b"one\r\ntwo\r\n",
                 "conv.py": b"import pathlib\npath = pathlib.Path('conv.txt')\n"
                            b"path.write_bytes(path.read_bytes().replace(b'\\r\\n', b'\\n'))\n"}
OUTPUT = ("Do these in order, one tool call each, and never retry a failed step. 1. Run the Bash command: "
          "seq 1 8000 2. Run the Bash command: echo IOPROBE_OUT; echo IOPROBE_ERR >&2; exit 1 3. Run the "
          "Bash command: grep -c nomatch s.txt && echo IOPROBE_AFTER 4. Run the Bash command: grep nomatch "
          "s.txt 5. Run the PowerShell command: Write-Output IOPROBE_SHAPE 6. Run the PowerShell command: "
          "1..8000 Then quote word for word the first line of each tool result.")
RESULTS = ("Do these in order, one tool call each, and never retry. 1. Run the Bash command: seq 1 8000 "
           "2. Run the Bash command: grep -c nomatch s.txt && echo IOPROBE_AFTER 3. Run the Bash command: "
           "python -c \"raise ValueError('boom')\" 2>&1 | tail -3 4. Run the PowerShell command: 1..8000 "
           "Then reply DONE.")
RESULTS_SEEN = ("OUTPUT_SAVED: The output was",
                "EXIT_BENIGN: Exit code 1 is the answer grep gives when no line matches",
                "PIPE_HIDES_EXIT: The output has 1 line that reports errors (1 exception)")
PIPE_TWICE = ("Do these in order, one tool call each, and never retry. 1. Run the Bash command: "
              "python -m unittest discover -s . 2>&1 | tail -3 2. Run the same Bash command again. Then "
              "reply DONE.")
PIPE_WARNED = "PIPE_HIDES_EXIT: This command pipes python -m unittest into tail"
INSTALLED = "io-guard@claude-io-guard"
ALIGNED_PY = (b"PROBES = {\n    \"a\": Probe(0, allowed=(\"Read\",),\n                 check=(\"a\",),\n"
              b"                 max_turns=8,\n                 setup={}),\n    \"b\": Probe(1),\n}\n")
DELETE_JOIN = ("Read f.txt. Then call the Edit tool once with exactly these arguments, changing none of "
               "them: {\"file_path\": \"f.txt\", \"old_string\": \"\\nb\", \"new_string\": \"\"} Then reply "
               "DONE.")
SCRIPT_GIVEN = "Run this exact Bash command and nothing else: python rewrite.py a.txt Then reply DONE."
REWRITE_PY = b"import sys\nwith open(sys.argv[1], 'w') as out:\n    out.write('two\\n')\n"
INDEX_ONLY = ("Do these in order, one tool call each, and never retry. 1. Run the Bash command: python -c "
              "\"open('n.txt', 'w').write('x')\" 2. Run the Bash command: git add n.txt 3. Run the Bash "
              "command: git reset -q n.txt Then reply DONE.")
IO_READ = "mcp__plugin_io-guard_io__io_read"
SERVER_READ = (f"Do these in order, one tool call each. 1. Run the Bash command: echo hi 2. Load {IO_READ} "
               f"with the ToolSearch tool, with the query select:{IO_READ} 3. Call {IO_READ} with path "
               "keep.txt. Then quote the first line of its result word for word.")
IO_EDIT = "mcp__plugin_io-guard_io__io_edit"
COUNT_STEPS = (
    f"1. Load {IO_EDIT} with the ToolSearch tool, with the query select:{IO_EDIT} 2. Call {IO_EDIT} ten "
    "times, one call at a time and never two in one message, each with the path counters.txt and one edit: "
    "the first call replaces {0}=0 with {0}=1, the second {0}=1 with {0}=2, and so on, until the tenth "
    "replaces {0}=9 with {0}=10. 3. If a call fails, quote its error word for word and stop.")
PARALLEL_EDITS = (
    "Start three subagents at once, with three Agent tool calls in one message, then wait for all three. "
    "Give each one its own steps, copied exactly as written here.\n"
    + "\n".join(f"Subagent {letter}: {COUNT_STEPS.format(letter)}" for letter in "ABC")
    + "\nWhen all three are done, reply DONE.")
IO_RUN = "mcp__plugin_io-guard_io__io_run"
IO_STATUS = "mcp__plugin_io-guard_io__io_status"
LOAD_RUN = (f"Load {IO_RUN} and {IO_STATUS} with the ToolSearch tool, with the query "
            f"select:{IO_RUN},{IO_STATUS}")
RUN_BODY = (
    f"Do these in order. 1. {LOAD_RUN} 2. Call {IO_RUN} once, with lang python and a code body of 252 lines, "
    "written out in full in that one call: first the line s = [] then 250 lines, where line NNN, for NNN "
    "from 001 to 250, is exactly: s.append(r'C:\\\\dir\\\\NNN')  # io-guard io.run transport check, padding "
    "line NNN of 250 and last the line print(len(s), s[-1]). Each of those lines holds two pairs of "
    "backslashes, two backslash characters side by side before dir and two before NNN, and the test is "
    "whether all four arrive, so write both of each pair. Then quote the last line of its result word for "
    "word.")
RUN_PRINTED = "250 C:\\\\dir\\\\250"
RUN_SLOW = (f"1. {LOAD_RUN} 2. Call {IO_RUN} with lang python, background true, and this code: import time\n"
            "for minute in range(15):\n    print('minute', minute, flush=True)\n    time.sleep(60)\n"
            f"3. Call {IO_STATUS} with the handle it returned. Then quote its state and reply DONE.",
            f"Call {IO_STATUS} again with the same handle. Then quote its state and exit code and reply "
            "DONE.")
RUN_RULES = {"permissions": {"deny": ["Bash(git push *)"], "ask": ["Bash(git fetch *)"]}}
RUN_DENIED = (f"Do these in order. 1. {LOAD_RUN} 2. Call {IO_RUN} with argv [\"git\", \"push\", \"origin\", "
              "\"main\"]. Then quote its result word for word and reply DONE.")
RUN_ASKED = (f"Do these in order. 1. {LOAD_RUN} 2. Call {IO_RUN} with argv [\"git\", \"fetch\", "
             "\"--dry-run\"]. Then quote its result, or any refusal, word for word and reply DONE.")
IO_SNAPSHOT = "mcp__plugin_io-guard_io__io_snapshot"
IO_RESTORE = "mcp__plugin_io-guard_io__io_restore"
IO_STAGE = "mcp__plugin_io-guard_io__io_stage"
STAGE_LINES = b"".join(f"line {number}\n".encode() for number in range(1, 31))
STAGE_STEPS = (
    f"Do these in order. 1. Load {IO_EDIT} and {IO_STAGE} with the ToolSearch tool, with the query "
    f"select:{IO_EDIT},{IO_STAGE} 2. Call {IO_EDIT} with path a.txt and two edits, old_string \"line 3\\n\" "
    "to new_string \"LINE 3\\n\", and old_string \"line 20\\n\" to new_string \"LINE 20\\n\". 3. Call "
    f"{IO_STAGE} with path a.txt and lines [{{\"first_line\": 3, \"last_line\": 3}}]. Then quote each "
    "result, or any refusal, word for word and reply DONE.")
RESTORE_STEPS = (
    f"Do these in order. 1. Load {IO_SNAPSHOT}, {IO_EDIT} and {IO_RESTORE} with the ToolSearch tool, with "
    f"the query select:{IO_SNAPSHOT},{IO_EDIT},{IO_RESTORE} 2. Call {IO_SNAPSHOT} with paths "
    f"[\"notes.txt\"] and tag \"probe\". 3. Call {IO_EDIT} with path notes.txt and one edit, old_string "
    f"\"one\" and new_string \"changed\". 4. Call {IO_RESTORE} with tag \"probe\". Then quote each result, "
    "or any refusal, word for word and reply DONE.")
GIT_RULES = {"permissions": {
    "ask": ["Bash(git commit *)", "Bash(git push *)", "PowerShell(git commit *)", "PowerShell(git push *)"],
    "deny": ["Bash(git reset --hard *)", "PowerShell(git reset --hard *)"]}}
GRANTED = ("This is a throwaway repository that tests a commit guard, and I grant the commits this message "
           "asks for. ")
COMMIT_ASKED = (GRANTED + "Do these in order, one Bash call each. 1. Run: git commit --allow-empty -m "
                "'feat: empty' 2. Run: git reset --hard HEAD Then say for each whether it ran, was denied, "
                "or needed approval, and reply DONE.")
COMMIT_POLICY = {"commit_policy": {"forbid": ["Co-Authored-By"]}}
VERIFY_PY = {"verify": {".py": ["python", "-m", "py_compile", "{file}"]}}
BROKEN_PY = ("Use the Write tool once to create bad.py with exactly this one line: def f(: Then reply DONE, "
             "without fixing anything.")
COMMIT_WITH_CO_AUTHOR = (GRANTED + "The co-author line is the test: the guard should refuse it. Run "
                         "exactly this Bash command: git commit --allow-empty -m 'feat: two' -m "
                         "'Co-Authored-By: Helper <helper@example.com>' If it is refused, commit again as "
                         "the refusal says, then reply DONE.")
INVISIBLE = ("Use the Write tool once to create strip.py with two lines. Line 1: import io. Line 2: raw = "
             "raw.lstrip('X'), where X is the byte order mark character itself, U+FEFF, and not an escape "
             "for it. Then quote word for word any note that came back with the Write, and reply DONE.")
IO_FORMAT = "mcp__plugin_io-guard_io__io_format"
FORMAT_STYLE = b"BasedOnStyle: LLVM\nLineEnding: LF\n"
FORMAT_CPP = b"\xef\xbb\xbfint  kept=1;\r\nint main() {\r\n  return 0;\r\n}\r\n"
FORMATTED_CPP = (b"\xef\xbb\xbfint  kept=1;\r\nint main() {\r\n  int y = 2;\r\n  if (y) {\r\n    y++;\r\n"
                 b"  }\r\n  return 0;\r\n}\r\n").decode("latin-1")
FORMAT_STEPS = (f"Do these in order, one tool call each. 1. Load {IO_EDIT} and {IO_FORMAT} with the "
                f"ToolSearch tool, with the query select:{IO_EDIT},{IO_FORMAT} 2. Call {IO_EDIT} with path "
                "a.cpp and one edit, whose old_string is exactly: return 0; and whose new_string is exactly: "
                f"int  y=2;if(y){{y++;}} return 0; 3. Call {IO_FORMAT} with paths [\"a.cpp\"]. Then quote "
                "its result word for word and reply DONE.")
FORMAT_DRY_STEPS = FORMAT_STEPS.replace('with paths ["a.cpp"].', 'with paths ["a.cpp"] and dry_run true.')
EDITED_CPP = FORMAT_CPP.replace(b"return 0;", b"int  y=2;if(y){y++;} return 0;").decode("latin-1")
SKILL_TURNS = ("Change one to two in notes.txt. Try this Bash command first: sed -i 's/one/two/' notes.txt",
               "List the running Python processes. Try this Bash command first: "
               "tasklist /FI \"IMAGENAME eq python.exe\"",
               "List the top folder of the Windows folder. Try this Bash command first: ls \"C:\\Windows\\\"",
               "Print the number 5 from a PowerShell variable. Try this PowerShell command first: "
               "$PID = 5; $PID",
               "List the files in this folder. Try this Bash command first: Get-ChildItem")
SKILL_REFUSALS = ("SHELL_WRITE", "MSYS_PATH", "TRAILING_BACKSLASH_QUOTE", "POWERSHELL_TRAP",
                  "DIALECT_MISMATCH")          # the code each turn's command meets, in turn order
LOOKUPS = ("Read", "Skill", "ToolSearch", "Glob", "Grep")
COUNTERS = b"\xef\xbb\xbfA=0\r\nB=0\r\nC=0\r\n"
COUNTED = b"\xef\xbb\xbfA=10\r\nB=10\r\nC=10\r\n".decode("latin-1")
SERVER_DIES = ("Run this exact Bash command: echo IOGUARD_DIE\nThen reply DONE.",
               "Run this exact Bash command: echo IOGUARD_TWO\nThen quote word for word any hook message or "
               "error you saw, and reply DONE.")
CONFORM_OFF = json.dumps({"checks": {"conform.write": {"enabled": False}}}).encode("ascii")
READ_ONLY = "Read Hero.uasset. Then use the Edit tool once on Hero.uasset to replace v1 with v2, and use " \
            "no other tool. Then quote word for word the error or note that came back."
LOCKED = "Read keep.txt. Then use the Edit tool once on keep.txt to replace alpha with beta. If it fails, " \
         "do not retry and use no other tool. Then quote word for word the error and every note that came " \
         "with it."
# GENERIC_READ, sharing reads only, as an editor or a build holds a file
HOLD = ("import sys, _winapi; handle = _winapi.CreateFile(sys.argv[1], 0x80000000, 1, 0, 3, 0, 0); "
        "print('open', flush=True); sys.stdin.read()")
ARROW = 'python -c "print(chr(0x2192))"'
DEFAULTS = f"Run these commands one at a time, each in its own tool call, and never retry. 1. Bash: " \
           f"{ARROW} 2. Bash: env -u PYTHONUTF8 -u PYTHONIOENCODING {ARROW} 3. PowerShell: {ARROW} " \
           "4. PowerShell: Write-Output \"utf8=$env:PYTHONUTF8\" Then reply DONE."
BASH_PRE = (("PreToolUse", "Bash", "exec"),)
BASH_GATE = (("PreToolUse", "Bash", "mcp"),)
FILE_AND_SHELL = ("Bash", "PowerShell", "Read", "Edit", "Write")
EVERY_GUARD_EVENT = (("PreToolUse", "", "guard"), ("PostToolUse", "", "guard"),
                     ("PostToolUseFailure", "", "guard"))


@dataclass(frozen=True)
class Probe:
    item: int
    mode: str
    prompt: str
    hooks: tuple = ()
    server: bool = False
    allowed: tuple = ()
    permission: str = "default"
    settings: dict | None = None
    env: dict = field(default_factory=dict)
    setup: dict = field(default_factory=dict)
    git: bool = False
    extra: dict = field(default_factory=dict)
    check: tuple = ()
    max_turns: int = 8
    model: str = "haiku"
    extra_args: tuple = ()
    guard: str | None = None     # run io-guard itself, with these test checks, instead of io-probe
    turns: tuple = ()            # prompts sent one at a time through stream-json input, instead of prompt
    pause_s: float = 0.0         # the wait after each turn's result before the next turn
    user_config: dict | None = None   # io-guard's config.json in the probes' folder, for this run only


PROBES = {
    "rewrite-allow": Probe(1, "rewrite_bash_allow", hooks=BASH_PRE, allowed=("Bash",),
                           prompt="Run this exact Bash command and nothing else: echo IOPROBE_ORIGINAL\n"
                                  "Then reply with the exact output line it printed."),
    "write-bytes": Probe(2, "rewrite_write", hooks=(("PreToolUse", "Write", "exec"),), allowed=("Write",),
                         check=("probe.txt",),
                         prompt="Use the Write tool once to create probe.txt in the current folder with the "
                                "content: hello\nThen reply DONE."),
    "edit-extend": Probe(3, "rewrite_edit", hooks=(("PreToolUse", "Edit", "exec"),),
                         allowed=("Read", "Edit"), setup={"edit.txt": b"alpha beta gamma\n"},
                         check=("edit.txt",),
                         prompt="Read edit.txt, then use the Edit tool once to replace the text beta with "
                                "BETA. Then reply DONE."),
    "read-context": Probe(4, "context_read", hooks=(("PostToolUse", "Read", "exec"),), allowed=("Read",),
                          setup={"note.txt": b"just a note\n"},
                          prompt="Read note.txt with the Read tool. Then quote word for word any text that "
                                 "came with that tool result besides the file's own line, such as an added "
                                 "note or context. If there was none, reply NONE."),
    "failures": Probe(5, "context_failure", allowed=("Read", "Edit", "Bash"), max_turns=14,
                      hooks=(("PostToolUseFailure", "", "exec"), ("PostToolUse", "", "exec")),
                      setup={"fail.txt": b"one\ntwo\n"}, prompt=FAILURES),
    "edit-refusals": Probe(5, "record", allowed=("Read", "Edit"), max_turns=12, prompt=EDIT_REFUSALS,
                           hooks=(("PreToolUse", "Edit", "exec"), ("PostToolUseFailure", "", "exec")),
                           setup={"f.txt": b"one\ntwo\nx\nx\n", "unread.txt": b"alpha\n"}),
    "other-refusals": Probe(5, "record", allowed=("Read", "Edit", "Write", "Grep", "Glob"), max_turns=14,
                            prompt=OTHER_REFUSALS,
                            hooks=(("PreToolUse", "", "exec"), ("PostToolUseFailure", "", "exec")),
                            setup={"big.txt": b"".join(b"line %06d of a large file to read whole\n" % n
                                                       for n in range(9000)), "kept.txt": b"kept\n"}),
    "bash-diff-off": Probe(6, "record", hooks=(("PostToolUse", "Bash", "exec"),), allowed=("Read", "Bash"),
                           git=True, setup={"diff.txt": b"a\n"}, check=("diff.txt",), prompt=SED),
    "bash-diff-on": Probe(6, "record", hooks=(("PostToolUse", "Bash", "exec"),), allowed=("Read", "Bash"),
                          settings={"bashEditDiffEnabled": True}, git=True, setup={"diff.txt": b"a\n"},
                          check=("diff.txt",), prompt=SED),
    "env-file": Probe(7, "envfile", hooks=(("SessionStart", "", "exec"), *BASH_PRE), allowed=("Bash",),
                      prompt='Run this exact Bash command: echo "export=$IOPROBE_ENV_EXPORT '
                             'plain=$IOPROBE_ENV_PLAIN"\nThen reply with the exact output line.'),
    "updated-output": Probe(8, "updated_output", hooks=(("PostToolUse", "Bash", "exec"),), allowed=("Bash",),
                            prompt="Run this exact Bash command: echo IOPROBE_REAL_OUTPUT\n"
                                   "Then reply with the exact output you saw, word for word."),
    "command-output": Probe(0, "command_output", allowed=("Bash", "PowerShell"), max_turns=12, prompt=OUTPUT,
                            hooks=(("PostToolUse", "", "exec"), ("PostToolUseFailure", "", "exec")),
                            setup={"s.txt": b"one\ntwo\n"}),
    "time-exec": Probe(9, "record", hooks=BASH_PRE, allowed=("Bash",), prompt=TEN_ECHOES, max_turns=14),
    "time-shell": Probe(9, "record", hooks=(("PreToolUse", "Bash", "shell"),), allowed=("Bash",),
                        prompt=TEN_ECHOES, max_turns=14),
    "hook-crash": Probe(10, "crash", hooks=BASH_PRE, allowed=("Bash",), check=("ran.txt",), prompt=RAN),
    "hook-timeout": Probe(10, "timeout", hooks=(("PreToolUse", "Bash", "exec", 3),), allowed=("Bash",),
                          extra={"sleep_s": 8}, check=("ran.txt",), prompt=RAN),
    "hook-badjson": Probe(10, "badjson", hooks=BASH_PRE, allowed=("Bash",), check=("ran.txt",), prompt=RAN),
    "time-mcp": Probe(12, "record", hooks=BASH_GATE, server=True, allowed=("Bash",), prompt=TEN_ECHOES,
                      max_turns=14),
    "mcp-gate": Probe(12, "mcp_gate_deny", hooks=BASH_GATE, server=True, allowed=("Bash",),
                      check=("gated.txt",),
                      prompt="Run this exact Bash command: echo IOPROBE_GATED > gated.txt\n"
                             "Then quote word for word the result, or the reason it did not run."),
    "mcp-subst": Probe(12, "record", server=True, allowed=("Bash", "Read", "Edit", "Write"), max_turns=10,
                       hooks=(*BASH_GATE, ("PreToolUse", "Edit", "mcp"), ("PreToolUse", "Write", "mcp")),
                       setup={"s.txt": b"one one\n"}, prompt=SUBSTITUTION),
    "ask-prompt": Probe(13, "rewrite_bash_ask", hooks=BASH_PRE, server=True, extra_args=PERMIT,
                        prompt="Run this exact Bash command and nothing else: echo IOPROBE_ORIGINAL\n"
                               "Then reply with the exact output line it printed."),
    "desktop": Probe(13, "rewrite_bash_ask", hooks=BASH_PRE, server=True, prompt=DESKTOP),
    "auto-control": Probe(14, "record", permission="auto", hooks=BASH_PRE, extra={"outside_dir": True},
                          model="sonnet", check=("../outside/keep.txt",), prompt=AUTO),
    "auto-allow": Probe(14, "allow_all", permission="auto", hooks=BASH_PRE, extra={"outside_dir": True},
                        model="sonnet", check=("../outside/keep.txt",), prompt=AUTO),
    "era-legacy": Probe(15, "record", server=True, allowed=(MCP + "probe_plain",), prompt=PLAIN_ONCE),
    "era-auto": Probe(15, "record", server=True, allowed=(MCP + "probe_plain",), prompt=PLAIN_ONCE,
                      env={"MCP_PROTOCOL_NEGOTIATION": "auto"}),
    "mcp-features": Probe(16, "record", server=True, prompt=THREE_FEATURES,
                          allowed=(MCP + "probe_elicit", MCP + "probe_progress", MCP + "probe_app")),
    "features-modern": Probe(16, "record", server=True, prompt=THREE_FEATURES,
                             env={"MCP_PROTOCOL_NEGOTIATION": "auto"},
                             allowed=(MCP + "probe_elicit", MCP + "probe_progress", MCP + "probe_app")),
    "mcp-prompts": Probe(17, "record", server=True,
                         prompt="Call these three tools from the io-probe server once each, in order: "
                                "probe_plain, probe_read, probe_destructive. For each one, say whether it "
                                "ran or was refused, and quote the message word for word."),
    "mcp-permit": Probe(17, "record", server=True, extra_args=PERMIT,
                        prompt="Call these three tools from the io-probe server once each, in order: "
                               "probe_plain, probe_read, probe_destructive. Then reply DONE."),
    "launch-mcp": Probe(0, "record", hooks=BASH_GATE, server=True, allowed=("Bash",),
                        prompt=HUNDRED_ECHOES, max_turns=115),
    "launch-exec": Probe(0, "record", hooks=BASH_PRE, allowed=("Bash",), prompt=HUNDRED_ECHOES,
                         max_turns=115),
    "launch-pyrun": Probe(0, "record", hooks=(("PreToolUse", "Bash", "pyrun"),), allowed=("Bash",),
                          prompt=HUNDRED_ECHOES, max_turns=115),
    "dead-server": Probe(18, "record", hooks=BASH_GATE, server=True, allowed=("Bash",),
                         extra={"die_after_gate": 1}, check=("first.txt", "second.txt"), prompt=TWO_RUNS),
    "dead-for-good": Probe(18, "record", hooks=BASH_GATE, server=True, allowed=("Bash",),
                           extra={"die_after_gate": 1, "stay_dead": True}, check=("first.txt", "second.txt"),
                           prompt=TWO_RUNS),
    "guard-fields": Probe(19, "record", hooks=EVERY_GUARD_EVENT, server=True, max_turns=12,
                          allowed=("Bash", "Read", "Edit", "Write"), setup={"s.txt": b"one\n"},
                          prompt=FIELDS),
    "guard-large": Probe(20, "record", hooks=(("PreToolUse", "Write", "guard"),), server=True,
                         allowed=("Write",), check=("big.txt",), prompt=LARGE,
                         env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "64000"}),
    "live-empty": Probe(0, "", guard="", max_turns=12, allowed=FILE_AND_SHELL, check=("w.txt",), prompt=LIVE),
    "live-broken": Probe(0, "", guard="broken,note", max_turns=12, allowed=FILE_AND_SHELL, check=("w.txt",),
                         prompt=LIVE),
    "live-answers": Probe(22, "", guard="refuse,rewrite,note", permission="bypassPermissions",
                          setup={"s.txt": b"one\n"}, prompt=ANSWERS),
    "live-refuse": Probe(0, "", guard="rewrite", permission="dontAsk", allowed=("Bash",), prompt=REFUSE_MODE),
    "live-probe": Probe(0, "", guard="", allowed=("Bash", "PowerShell"), prompt=DEFAULTS),
    "live-move-ask": Probe(0, "record", guard="", server=True, extra_args=PERMIT, prompt=MOVED,
                           env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16000"}),
    "live-move-auto": Probe(0, "record", guard="", permission="auto", model="sonnet", prompt=MOVED,
                            env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16000"}),
    "write-quiet": Probe(0, "rewrite_write_quiet", hooks=(("PreToolUse", "Write", "exec"),), server=True,
                         extra_args=PERMIT, check=("probe.txt",),
                         prompt="Use the Write tool once to create probe.txt in the current folder with the "
                                "content: hello\nThen reply DONE."),
    "edit-trailing": Probe(0, "edit_trailing", hooks=(("PreToolUse", "Edit", "exec"),),
                           allowed=("Read", "Edit"), setup={"one.txt": b"one = 1\ntwo = 2\n"},
                           check=("one.txt",), prompt=TRAILING),
    "live-read-profile": Probe(0, "", guard="", allowed=("Read",), prompt=READ_PROFILE,
                               setup={"profiled.txt": b"\xef\xbb\xbfint x;\r\n\tint y;\r\n"}),
    "live-conform": Probe(0, "", guard="", permission="acceptEdits", allowed=("Read", "Write"),
                          prompt=CONFORM, check=("keep.txt",),
                          setup={"keep.txt": b"\xef\xbb\xbfalpha\r\nbeta\r\n"}),
    "live-verify": Probe(0, "", guard="", permission="acceptEdits", allowed=("Read", "Write", "Edit"),
                         prompt=VERIFY, check=("keep.txt",), max_turns=10,
                         setup={"keep.txt": b"\xef\xbb\xbfalpha\r\nbeta\r\n",
                                ".claude/io-guard.json": CONFORM_OFF}),
    "live-read-only": Probe(0, "", guard="", permission="acceptEdits", allowed=("Read", "Edit"), git=True,
                            prompt=READ_ONLY, check=("Hero.uasset",), extra={"readonly": ("Hero.uasset",)},
                            setup={".gitattributes": b"*.uasset lockable\n", "Hero.uasset": b"hero v1\n"}),
    "live-space-dropped": Probe(0, "", guard="", permission="acceptEdits", allowed=("Read", "Edit"),
                                prompt=SPACE_DROPPED, check=("ws.txt",), max_turns=10,
                                setup={"ws.txt": SPACE_DROPPED_FILE}),
    "live-locked": Probe(0, "", guard="", permission="acceptEdits", allowed=("Read", "Edit"), prompt=LOCKED,
                         check=("keep.txt",), extra={"hold": "keep.txt"}, setup={"keep.txt": b"alpha\n"}),
    "live-diagnose": Probe(0, "", guard="", permission="acceptEdits", prompt=DIAGNOSE, max_turns=16,
                           allowed=("Read", "Edit", "Grep", "Glob"),
                           setup={"a.cpp": DIAGNOSE_CPP,
                                  "big.txt": b"".join(b"line %06d of a large file to read whole\n" % n
                                                      for n in range(9000))}),
    "live-touched": Probe(0, "", guard="", allowed=("Read", "Bash"), git=True, prompt=TOUCHED,
                          check=("a.cpp", "conv.txt"), setup=TOUCHED_FILES),
    "live-pipe-once": Probe(0, "", guard="", allowed=("Bash",), prompt=PIPE_TWICE, max_turns=6),
    "live-read-width": Probe(0, "", guard="", allowed=("Read",), prompt="Read p.py with the Read tool. Then "
                             "reply DONE.", setup={"p.py": ALIGNED_PY}),
    "edit-delete-join": Probe(0, "record", allowed=("Read", "Edit"), permission="acceptEdits",
                              prompt=DELETE_JOIN, check=("f.txt",), setup={"f.txt": b"a\nb\nc\n"}),
    "live-lines-joined": Probe(0, "", guard="", allowed=("Read", "Edit"), permission="acceptEdits",
                               prompt=DELETE_JOIN.replace("Then reply", "If the Edit is refused, do what the "
                                                          "refusal says. Then reply"),
                               check=("f.txt",), setup={"f.txt": b"a\nb\nc\n"}, max_turns=8),
    "live-script-write": Probe(0, "", guard="", allowed=("Bash",), git=True, prompt=SCRIPT_GIVEN, max_turns=4,
                               check=("a.txt",), setup={"a.txt": b"one\n", "rewrite.py": REWRITE_PY}),
    "live-touched-index": Probe(0, "", guard="", allowed=("Bash",), git=True, prompt=INDEX_ONLY, max_turns=8,
                                setup={"a.txt": b"a\n"}),
    "live-results": Probe(0, "", guard="", allowed=("Bash", "PowerShell"), prompt=RESULTS, max_turns=10,
                          setup={"s.txt": b"one\ntwo\n"}),
    "live-server": Probe(0, "", guard="", allowed=("Bash", "ToolSearch", IO_READ), prompt=SERVER_READ,
                         setup={"keep.txt": b"\xef\xbb\xbfalpha\r\nbeta\r\n"}),
    "live-server-modern": Probe(0, "", guard="", allowed=("Bash", "ToolSearch", IO_READ), prompt=SERVER_READ,
                                env={"MCP_PROTOCOL_NEGOTIATION": "auto"},
                                setup={"keep.txt": b"\xef\xbb\xbfalpha\r\nbeta\r\n"}),
    "live-server-down": Probe(0, "", guard="die", allowed=("Bash",), prompt="", turns=SERVER_DIES, pause_s=40,
                              extra={"dead_marker": True}),
    "live-verify-direct": Probe(0, "", guard="", permission="acceptEdits", allowed=("Read", "Write", "Edit"),
                                prompt=VERIFY_DIRECT, check=("keep.txt",), max_turns=10,
                                setup={"keep.txt": b"\xef\xbb\xbfalpha\r\nbeta\r\n",
                                       ".claude/io-guard.json": CONFORM_OFF}),
    "live-edit-parallel": Probe(0, "", guard="", allowed=("Agent", "Task", "ToolSearch", IO_EDIT),
                                prompt=PARALLEL_EDITS, check=("counters.txt",), max_turns=12,
                                setup={"counters.txt": COUNTERS}),
    "live-run-body": Probe(0, "", guard="", allowed=("ToolSearch", IO_RUN, IO_STATUS), prompt=RUN_BODY,
                           env={"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "64000"}),
    "live-run-background": Probe(0, "", guard="", allowed=("ToolSearch", IO_RUN, IO_STATUS), prompt="",
                                 turns=RUN_SLOW, pause_s=960),
    "live-run-denied": Probe(0, "", guard="", allowed=("ToolSearch", IO_RUN, IO_STATUS), prompt=RUN_DENIED,
                             setup={".claude/settings.json": json.dumps(RUN_RULES).encode("ascii")}),
    "live-run-asked": Probe(0, "record", guard="", server=True, extra_args=PERMIT,
                            allowed=("ToolSearch", IO_RUN, IO_STATUS), prompt=RUN_ASKED,
                            setup={".claude/settings.json": json.dumps(RUN_RULES).encode("ascii")}),
    "live-restore": Probe(0, "record", guard="", server=True, extra_args=PERMIT,
                          allowed=("ToolSearch", IO_SNAPSHOT, IO_EDIT, IO_RESTORE), prompt=RESTORE_STEPS,
                          check=("notes.txt",), setup={"notes.txt": b"one\r\ntwo\r\n"}),
    "live-stage": Probe(0, "", guard="", allowed=("ToolSearch", IO_EDIT, IO_STAGE), prompt=STAGE_STEPS,
                        git=True, setup={"a.txt": STAGE_LINES}),
    "live-format": Probe(0, "", guard="", allowed=("ToolSearch", IO_EDIT, IO_FORMAT), prompt=FORMAT_STEPS,
                         git=True, check=("a.cpp",),
                         setup={".clang-format": FORMAT_STYLE, "a.cpp": FORMAT_CPP}),
    "live-format-dry": Probe(0, "", guard="", allowed=("ToolSearch", IO_EDIT, IO_FORMAT),
                             prompt=FORMAT_DRY_STEPS, git=True, check=("a.cpp",),
                             setup={".clang-format": FORMAT_STYLE, "a.cpp": FORMAT_CPP}),
    "live-skill": Probe(0, "", guard="", permission="dontAsk", allowed=(*FILE_AND_SHELL, "Skill"), prompt="",
                        turns=SKILL_TURNS, git=True, max_turns=24, setup={"notes.txt": b"one\n"}),
    "live-skill-doctor": Probe(0, "", guard="", prompt="/skill-doctor", max_turns=4),
    "live-invisible": Probe(0, "", guard="", permission="acceptEdits", allowed=("Write",), prompt=INVISIBLE,
                            check=("strip.py",)),
    "live-commit-asked": Probe(0, "record", guard="", server=True, permission="auto", model="sonnet",
                               extra_args=PERMIT, prompt=COMMIT_ASKED, git=True, setup={"notes.txt": b"one\n",
                               ".claude/settings.json": json.dumps(GIT_RULES).encode("ascii")}),
    "live-commit-policy": Probe(0, "", guard="", permission="dontAsk", allowed=("Bash",), git=True,
                                prompt=COMMIT_WITH_CO_AUTHOR, user_config=COMMIT_POLICY,
                                setup={"notes.txt": b"one\n"}),
    "live-verify-output": Probe(0, "", guard="", permission="acceptEdits", allowed=("Write",),
                                prompt=BROKEN_PY, user_config=VERIFY_PY, max_turns=4),
}


def handler(event: str, form: str, timeout: int | None) -> dict:
    match form:
        case "exec":
            entry = {"type": "command", "command": str(PYTHON),
                     "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/probe_hook.py", "exec"]}
        case "shell":
            script = '"${CLAUDE_PLUGIN_ROOT}/scripts/probe_hook.py"'
            entry = {"type": "command", "command": f'"{PYTHON.as_posix()}" {script} shell'}
        case "mcp":
            entry = {"type": "mcp_tool", "server": SERVER, "tool": "hook_gate", "input": GATE_INPUT}
        case "guard":
            entry = {"type": "mcp_tool", "server": SERVER, "tool": "hook_gate", "input": GUARD_INPUTS[event]}
        case "pyrun":
            entry = {"type": "command", "command": f'sh "{PYRUN}" "{HOOK_PY}" pre_tool_use'}
        case _:
            raise ValueError(f"unknown hook form {form}")
    if timeout is not None:
        entry["timeout"] = timeout
    return entry


def hooks_config(probe: Probe) -> dict:
    events: dict = {}
    for event, matcher, form, *rest in probe.hooks:
        group = {"hooks": [handler(event, form, rest[0] if rest else None)]}
        if matcher:
            group["matcher"] = matcher
        events.setdefault(event, []).append(group)
    return {"hooks": events}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2) + "\n").encode("ascii"))


def assemble(name: str, probe: Probe, plugin: Path, log: Path) -> None:
    shutil.copytree(HERE / "plugin" / "scripts", plugin / "scripts",
                    ignore=shutil.ignore_patterns("__pycache__"))
    write_json(plugin / ".claude-plugin" / "plugin.json",
               {"name": "io-probe", "description": f"io-guard harness probe: {name}"})
    write_json(plugin / "hooks" / "hooks.json", hooks_config(probe))
    if probe.server:
        server = {"command": str(PYTHON), "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/probe_server.py"],
                  "env": {"PYTHONUTF8": "1"}}
        write_json(plugin / ".mcp.json", {"mcpServers": {"probe": server}})
    nonce = f"{name}-{time.strftime('%H%M%S')}"
    write_json(plugin / "probe.json", {"mode": probe.mode, "nonce": nonce, "log": str(log), **probe.extra})


def git(work: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=work, check=True, capture_output=True,
                   timeout=60)


def prepare_work(probe: Probe, work: Path) -> None:
    work.mkdir(parents=True)
    for rel, data in probe.setup.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_bytes(data)
    if probe.extra.get("outside_dir"):
        (work.parent / "outside").mkdir()
        (work.parent / "outside" / "keep.txt").write_bytes(b"keep\n")
    if probe.git:
        identity = ("-c", "user.name=io-probe", "-c", "user.email=probe@localhost")
        git(work, "init", "-q", "-b", "main")
        git(work, *identity, "add", "-A")
        git(work, *identity, "commit", "-q", "-m", "probe")
    for rel in probe.extra.get("readonly", ()):
        os.chmod(work / rel, stat.S_IREAD)


def hold(path: Path) -> subprocess.Popen:
    """A Python child that holds path open until its stdin closes, as an editor or a build holds a file."""
    child = subprocess.Popen([sys.executable, "-c", HOLD, str(path)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE)
    child.stdout.readline()
    return child


def hook_durations(lines: list[bytes], arrivals: list[int]) -> list[dict]:
    """Time each hook from the arrival of its hook_started line to the arrival of its hook_response line."""
    started, durations = {}, []
    for line, arrived in zip(lines, arrivals):
        try:
            message = json.loads(line)
        except ValueError:
            continue
        match message.get("subtype"):
            case "hook_started":
                started[message.get("hook_id")] = arrived
            case "hook_response" if message.get("hook_id") in started:
                elapsed = (arrived - started.pop(message["hook_id"])) / 1e6
                durations.append({"hook": message.get("hook_name"), "ms": round(elapsed, 1),
                                  "outcome": message.get("outcome"), "exit_code": message.get("exit_code")})
    return durations


def summarise(stream: Path, log: Path, work: Path, probe: Probe) -> dict:
    tools, results, hook_events, notes = [], [], [], []
    final = None
    for line in stream.read_bytes().decode("utf-8", "replace").splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            notes.append(line[:300])
            continue
        kind, subtype = message.get("type"), str(message.get("subtype", ""))
        if kind == "system" and subtype == "init":
            notes.append({"mcp_servers": message.get("mcp_servers"),
                          "version": message.get("claude_code_version"),
                          "permissionMode": message.get("permissionMode")})
        elif kind == "system" and subtype.startswith("hook"):
            hook_events.append({key: (value[:600] if isinstance(value, str) else value)
                                for key, value in message.items() if key not in ("uuid", "session_id")})
        elif kind == "system" and subtype not in ("thinking_tokens", "task_summary"):
            notes.append(message)
        elif kind in ("assistant", "user"):
            for block in (message.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    tools.append({"name": block.get("name"), "input": block.get("input")})
                elif block.get("type") == "tool_result":
                    results.append({"is_error": block.get("is_error"), "content": block.get("content")})
        elif kind == "result":
            keys = ("result", "is_error", "permission_denials", "num_turns")
            final = {key: message.get(key) for key in keys}
        elif kind != "system":
            notes.append(message)
    lines = [json.loads(line) for line in log.read_bytes().splitlines()] if log.exists() else []
    files = {rel: ((work / rel).read_bytes().decode("latin-1") if (work / rel).exists() else None)
             for rel in probe.check}
    return {"tools": tools, "results": results, "hook_events": hook_events, "final": final, "notes": notes,
            "probe_log": lines, "files": files}


def guarded(probe: Probe) -> tuple[dict, dict]:
    """The settings and environment that run io-guard from this checkout with the probe's test checks: this
    Python as IOGUARD_PYTHON, and tests/support/inject on PYTHONPATH."""
    env = {"IOGUARD_PYTHON": str(PYTHON), "IOGUARD_HOME": str(GUARD_HOME), "PYTHONPATH": str(INJECT),
           "IOGUARD_TEST_CHECKS": probe.guard}
    return probe.settings, env


def copy_telemetry(lines: list[bytes], log: Path) -> None:
    """io-guard's telemetry for the session the stream names, as the run's log."""
    for line in lines:
        message = json.loads(line) if line.startswith(b"{") else {}
        if message.get("type") == "system" and message.get("subtype") == "init":
            found = sorted(GUARD_HOME.glob(f"events/*/{message.get('session_id')}.jsonl"))
            if found:
                shutil.copyfile(found[-1], log)
            return


def forget_failed_start(server: str) -> bool:
    """Remove the failed start Claude Code cached for server in mcp-needs-auth-cache.json, which would skip
    the server in every session for the next 15 minutes. True when there was one to remove."""
    if not NEEDS_AUTH.is_file():
        return False
    cache = json.loads(NEEDS_AUTH.read_bytes())
    if cache.pop(server, None) is None:
        return False
    NEEDS_AUTH.write_bytes(json.dumps(cache).encode("ascii"))
    return True


def feed(session: subprocess.Popen, probe: Probe, answered: threading.Semaphore) -> None:
    """Send each turn as a stream-json user message, the next one pause_s after the last one's result, and
    close stdin after the last result."""
    for index, text in enumerate(probe.turns):
        if index:
            answered.acquire(timeout=300)
            time.sleep(probe.pause_s)
        message = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        session.stdin.write(json.dumps(message).encode("utf-8") + b"\n")
        session.stdin.flush()
    answered.acquire(timeout=300)
    session.stdin.close()


@contextlib.contextmanager
def user_config(values: dict | None):
    """values as io-guard's user config.json in the probes' io-guard folder for the with block, then the
    file as it was before, or none."""
    if values is None:
        yield
        return
    path = GUARD_HOME / "config.json"
    before = path.read_bytes() if path.is_file() else None
    write_json(path, values)
    try:
        yield
    finally:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(before)


def without_installed(settings: dict | None) -> dict:
    """settings with the lead's installed io-guard off. A user setting enables it in every session, the CLI
    loads it from this checkout, and a probe runs io-guard through --plugin-dir or not at all."""
    found = dict(settings or {})
    found["enabledPlugins"] = {**found.get("enabledPlugins", {}), INSTALLED: False}
    return found


def run(name: str) -> Path:
    probe = PROBES[name]
    out = OUT / name / time.strftime("%Y%m%d-%H%M%S")
    plugin, work, log = out / "plugin", out / "work", out / "probe.jsonl"
    settings, env, helper = probe.settings, probe.env, ()
    if probe.guard is None:
        assemble(name, probe, plugin, log)
    else:
        if probe.server:        # io-probe rides along for its probe_permit tool, and records what it approves
            assemble(name, probe, plugin, out / "permit.jsonl")
            helper = ("--plugin-dir", str(plugin))
        plugin = GUARD
        settings, extra = guarded(probe)
        env = {**env, **extra}
    prepare_work(probe, work)
    if probe.extra.get("dead_marker"):
        env = {**env, "IOGUARD_TEST_DEAD": str(out / "dead.marker")}
    holder = hold(work / probe.extra["hold"]) if "hold" in probe.extra else None
    claude = os.environ.get("IOPROBE_CLAUDE", "claude")
    prompt = ["--input-format", "stream-json"] if probe.turns else [probe.prompt]
    argv = [claude, "-p", *prompt, "--plugin-dir", str(plugin), *helper, "--output-format",
            "stream-json", "--verbose", "--include-hook-events", "--debug-file", str(out / "debug.txt"),
            "--permission-mode", probe.permission, "--model", probe.model,
            "--max-turns", str(probe.max_turns), *probe.extra_args]
    if probe.allowed:
        argv += ["--allowedTools", *probe.allowed]
    settings = without_installed(settings)
    if settings is not None:
        argv += ["--settings", json.dumps(settings)]
    started = time.time()
    lines, arrivals = [], []
    answered = threading.Semaphore(0)
    with (out / "stderr.txt").open("wb") as stderr, user_config(probe.user_config):
        session = subprocess.Popen(argv, cwd=work, stdout=subprocess.PIPE, stderr=stderr,
                                   stdin=subprocess.PIPE if probe.turns else None, env={**os.environ, **env})
        killer = threading.Timer(600 + probe.pause_s * len(probe.turns), session.kill)
        killer.start()
        if probe.turns:
            threading.Thread(target=feed, args=(session, probe, answered), daemon=True).start()
        for line in session.stdout:
            arrivals.append(time.time_ns())
            lines.append(line)
            if probe.turns and line.startswith(b"{") and json.loads(line).get("type") == "result":
                answered.release()
        exit_code = session.wait()
        killer.cancel()
    if holder is not None:
        holder.communicate(b"", timeout=30)
    skip_cached = forget_failed_start("plugin:io-guard:io") if probe.extra.get("dead_marker") else None
    (out / "stream.jsonl").write_bytes(b"".join(lines))
    if probe.guard is not None:
        copy_telemetry(lines, log)
        if (GUARD_HOME / "probe.json").is_file():
            shutil.copyfile(GUARD_HOME / "probe.json", out / "guard-probe.json")
    details = summarise(out / "stream.jsonl", log, work, probe)
    versions = [note["version"] for note in details["notes"] if isinstance(note, dict) and "version" in note]
    summary = {"probe": name, "item": probe.item, "claude": versions[0] if versions else None,
               "exit": exit_code, "seconds": round(time.time() - started, 1),
               "hook_ms": hook_durations(lines, arrivals), "skip_cached": skip_cached, **details}
    write_json(out / "summary.json", summary)
    return out


def latest(name: str) -> tuple[Path, dict]:
    folder = sorted((OUT / name).iterdir())[-1]
    return folder, json.loads((folder / "summary.json").read_bytes())


def brief(name: str) -> dict:
    """The parts of a run's summary a reader checks first, each cut to a readable length."""
    _, summary = latest(name)
    hook_keys = ("subtype", "hook_name", "outcome", "exit_code", "output", "stderr")
    log_keys = ("form", "answer", "received", "sent", "gate_args", "env_file_written", "dying")
    return {
        "probe": name, "claude": summary.get("claude"), "exit": summary["exit"],
        "seconds": summary["seconds"],
        "tools": [f"{tool['name']} {json.dumps(tool['input'])[:240]}" for tool in summary["tools"]],
        "results": [json.dumps(result)[:400] for result in summary["results"]],
        "final": summary["final"], "files": summary["files"], "hook_ms": summary["hook_ms"],
        "hooks": [{key: event.get(key) for key in hook_keys} for event in summary["hook_events"]
                  if event.get("hook_name") != "SessionStart:startup" or "io-probe" in json.dumps(event)],
        "probe_log": [json.dumps({key: line[key] for key in log_keys if line.get(key) is not None})[:500]
                      for line in summary["probe_log"]],
    }


def timing(name: str) -> str | None:
    _, summary = latest(name)
    times = sorted(hook["ms"] for hook in summary["hook_ms"] if hook["hook"].startswith("PreToolUse"))
    if not times:
        return None
    p95 = times[min(len(times) - 1, round(0.95 * (len(times) - 1)))]
    return (f"{name}: n={len(times)} min={times[0]} p50={times[len(times) // 2]} p95={p95} "
            f"max={times[-1]} ms")


def seen(summary: dict) -> str:
    """Everything the model saw and said in a run, as one string to search."""
    return json.dumps([summary["results"], summary["final"]])


def logged(summary: dict, needle: str) -> bool:
    return any(needle in json.dumps(line) for line in summary["probe_log"])


def debug_has(name: str, needle: str) -> bool:
    folder, _ = latest(name)
    return needle in (folder / "debug.txt").read_bytes().decode("utf-8", "replace")


def context_reached(name: str, needle: str) -> bool:
    """A hook's additionalContext holding needle is in the session transcript, as the attachment the model
    reads. The model's own summary of what it saw leaves lines out, so the verdicts read the transcript."""
    return context_count(name, needle) > 0


def context_count(name: str, needle: str) -> int:
    """How many of the session transcript's hook_additional_context attachments hold needle."""
    folder, _ = latest(name)
    project = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(folder / "work"))
    attachments = [json.loads(line).get("attachment") or {} for path in project.glob("*.jsonl")
                   for line in path.read_bytes().splitlines()]
    return sum(1 for attachment in attachments if attachment.get("type") == "hook_additional_context"
               and needle in json.dumps(attachment))


def index_left_alone(summary: dict, name: str) -> bool:
    """The three commands ran, the one that created n.txt was named, and git add and git reset were not."""
    ran = [call for call in calls(name) if call["name"] == "Bash" and not call["error"]]
    return (len(ran) == 3 and context_count(name, "TOUCHED_BY_SHELL") == 1
            and context_reached(name, "TOUCHED_BY_SHELL: This command created n.txt"))


def piped_twice_warned_once(summary: dict, name: str) -> bool:
    """Both piped runs happened, and the warning before a run reached the model once."""
    runs = [call for call in calls(name) if call["name"] == "Bash" and "unittest" in str(call["input"])]
    return len(runs) == 2 and context_count(name, PIPE_WARNED) == 1


def defaults_applied(summary: dict, name: str) -> bool:
    """The arrow printed through Bash, the same command without the defaults failed, and the session probe
    named the Claude Code version."""
    folder, _ = latest(name)
    saved = folder / "guard-probe.json"
    probe = json.loads(saved.read_bytes()) if saved.is_file() else {}
    outputs = [str(result["content"]) for result in summary["results"]]
    return (len(outputs) >= 2 and chr(0x2192) in outputs[0] and "UnicodeEncodeError" in outputs[1]
            and probe.get("claude_code_version") is not None)


def printed(summary: dict, text: str) -> bool:
    return any(str(result["content"]).strip() == text for result in summary["results"])


def asked_with_moved_body(summary: dict, name: str) -> bool:
    """The permission prompt carried the moved command, and the approved command printed 3."""
    folder, _ = latest(name)
    permit = folder / "permit.jsonl"
    lines = permit.read_bytes().decode("utf-8").splitlines() if permit.is_file() else []
    shown = any("probe_permit" in line and "python - < " in line for line in lines)
    return shown and printed(summary, "3")


def every_call_denied(summary: dict) -> bool:
    """Every probe tool the model called was denied for want of permission, and it called at least one."""
    called = {tool["name"] for tool in summary["tools"] if tool["name"].startswith(MCP)}
    denied = {denial.get("tool_name") for denial in summary["final"]["permission_denials"]}
    return bool(called) and called <= denied


def large_arrived(summary: dict) -> bool:
    """The Write's content reached the hook whole: as long as the file it wrote, and 125,000 bytes or more."""
    written = summary["files"]["big.txt"]
    for line in summary["probe_log"]:
        tool_input = (line.get("gate_args") or {}).get("tool_input") or ""
        content = json.loads(tool_input).get("content", "") if tool_input.startswith("{") else ""
        if written is not None and len(content.encode("utf-8")) == len(written) >= 125_000:
            return True
    return False


def guarded_every_call(summary: dict) -> bool:
    """io-guard recorded a PreToolUse line for every guarded tool call, and a PostToolUseFailure line."""
    runs = [line["event"] for line in summary["probe_log"] if line.get("check") is None]
    called = sum(tool["name"] in FILE_AND_SHELL for tool in summary["tools"])
    pre, failures = runs.count("PreToolUse"), runs.count("PostToolUseFailure")
    return called > 0 and pre == called and failures > 0


BOM_CRLF = b"\xef\xbb\xbfline one\r\nline two\r\n".decode("latin-1")
KEPT_CONFORMED = b"\xef\xbb\xbfgamma\r\ndelta\r\n".decode("latin-1")
KEPT_EDITED = tuple((b"\xef\xbb\xbfGAMMA\r\ndelta" + end).decode("latin-1") for end in (b"", b"\r\n"))


def hooks_started(summary: dict, tool: str) -> set[str]:
    """The hook names, such as PreToolUse:Edit, that started for one tool in a run."""
    return {event["hook_name"] for event in summary["hook_events"]
            if event.get("subtype") == "hook_started" and event.get("hook_name", "").endswith(f":{tool}")}


def repaired_then_edited(summary: dict, name: str, calls: list[str]) -> bool:
    """verify.write put back the BOM and CRLF a Write dropped, the calls ran in order with no error, and the
    Edit after the repair landed in the file's own bytes. The model decides the final newline."""
    return (summary["files"]["keep.txt"] in KEPT_EDITED
            and [tool["name"] for tool in summary["tools"]] == calls
            and not any(result["is_error"] for result in summary["results"])
            and context_reached(name, "EOL_CONVERTED: The Write tool left keep.txt"))


def served(summary: dict, name: str, era: str) -> bool:
    """io-guard's server connected, io.read named keep.txt's CRLF and BOM, and the server's heartbeat, which
    it marks stopped at the end of the session, recorded the MCP era it used."""
    folder, _ = latest(name)
    lines = [json.loads(line) for line in (folder / "stream.jsonl").read_bytes().splitlines()
             if line.startswith(b"{")]
    init = next(line for line in lines if line.get("subtype") == "init")
    connected = any(server.get("name") == "plugin:io-guard:io" and server.get("status") == "connected"
                    for server in init.get("mcp_servers") or ())
    read = any("CRLF, BOM" in str(result["content"]) for result in summary["results"])
    beat = GUARD_HOME / "sessions" / f"{init['session_id']}.alive"
    recorded = beat.is_file() and json.loads(beat.read_bytes()).get("era") == era
    return connected and read and recorded


def down_named(summary: dict, name: str) -> bool:
    """The second turn's UserPromptSubmit hook named SERVER_DOWN, that turn's command still ran, and Claude
    Code cached the failed restart, which the run then removed."""
    warned = any("SERVER_DOWN" in json.dumps(event) for event in summary["hook_events"]
                 if "UserPromptSubmit" in str(event.get("hook_name")))
    ran = any("IOGUARD_TWO" in str(result["content"]) for result in summary["results"])
    return warned and ran and summary.get("skip_cached") is True


def edits_interleaved(summary: dict, name: str) -> bool:
    """All 30 io.edit calls landed, so each counter ends at 10 in the file's BOM and CRLF, and the three
    subagents' calls interleaved in the stream, so the one server took them at the same time."""
    folder, _ = latest(name)
    owners = []
    for line in (folder / "stream.jsonl").read_bytes().splitlines():
        message = json.loads(line) if line.startswith(b"{") else {}
        if message.get("type") != "assistant":
            continue
        blocks = (message.get("message") or {}).get("content") or []
        owners += [message.get("parent_tool_use_id") for block in blocks
                   if block.get("type") == "tool_use" and block.get("name") == IO_EDIT]
    runs = sum(1 for index, owner in enumerate(owners) if index == 0 or owner != owners[index - 1])
    return summary["files"]["counters.txt"] == COUNTED and len(owners) == 30 and runs > len(set(owners))


def structured(summary: dict) -> list[dict]:
    """Each tool result the model read as a JSON object, which an io tool's structuredContent is."""
    found = []
    for result in summary["results"]:
        content = result["content"]
        texts = [content] if isinstance(content, str) else [block.get("text", "") for block in content or []
                                                            if isinstance(block, dict)]
        for text in texts:
            try:
                value = json.loads(text)
            except ValueError:
                continue
            if isinstance(value, dict):
                found.append(value)
    return found


def body_ran(summary: dict, name: str) -> bool:
    """A body of 20,000 bytes or more reached its file byte for byte, and Python printed each pair of
    backslashes whole."""
    sent = next((tool["input"].get("code") for tool in summary["tools"] if tool["name"] == IO_RUN), None)
    bodies = sorted(GUARD_HOME.glob("runs/*/body.py"), key=lambda path: path.stat().st_mtime)
    exact = sent is not None and bodies != [] and bodies[-1].read_bytes() == sent.encode("utf-8")
    printed = any(RUN_PRINTED in value.get("tail", []) for value in structured(summary))
    return exact and len(sent.encode("utf-8")) >= 20_000 and printed


def ran_in_background(summary: dict, name: str) -> bool:
    """io.status said running during the run, then ended with exit code 0 after 15 minutes."""
    states = [value for value in structured(summary) if "state" in value and value.get("handle")]
    return (len(states) >= 2 and states[0]["state"] == "running" and states[-1]["state"] == "ended"
            and states[-1]["exit"] == 0 and states[-1]["duration_s"] >= 900)


def run_asked(summary: dict, name: str) -> bool:
    """The hook answered ask with RULE_ASKED, and the permission prompt tool received the io.run call."""
    folder, _ = latest(name)
    permit = folder / "permit.jsonl"
    lines = permit.read_bytes().decode("utf-8").splitlines() if permit.is_file() else []
    prompted = any("probe_permit" in line and IO_RUN in line for line in lines)
    asked = any("RULE_ASKED" in json.dumps(event) for event in summary["hook_events"])
    return prompted and asked


def restore_asked(summary: dict, name: str) -> bool:
    """The hook answered ask with RESTORE_ASKED, the permission prompt tool received the io.restore call, and
    notes.txt holds its bytes from before the edit again."""
    folder, _ = latest(name)
    permit = folder / "permit.jsonl"
    lines = permit.read_bytes().decode("utf-8").splitlines() if permit.is_file() else []
    prompted = any("probe_permit" in line and IO_RESTORE in line for line in lines)
    asked = any("RESTORE_ASKED" in json.dumps(event) for event in summary["hook_events"])
    return prompted and asked and summary["files"].get("notes.txt") == "one\r\ntwo\r\n"


def staged_one_hunk(summary: dict, name: str) -> bool:
    """After io.edit changed lines 3 and 20, io.stage staged line 3 alone: the index holds LINE 3, the working
    tree's diff still holds LINE 20, and nothing was committed."""
    folder, _ = latest(name)
    work = folder / "work"
    cached, left = (subprocess.run(["git", *args, "--", "a.txt"], cwd=work, capture_output=True,
                                   timeout=60).stdout for args in (("diff", "--cached"), ("diff",)))
    commits = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=work, capture_output=True,
                             timeout=60).stdout.strip()
    return (b"+LINE 3" in cached and b"LINE 20" not in cached and b"+LINE 20" in left
            and b"LINE 3" not in left and commits == b"1")


def dry_run_shown(summary: dict, name: str) -> bool:
    """io.format with dry_run returned the diff of the edited lines and wrote nothing: the file holds the edit
    exactly as io.edit left it, badly formatted."""
    diffs = [each.get("diff", "") for value in structured(summary) for each in value.get("files", ())]
    return summary["files"]["a.cpp"] == EDITED_CPP and any("+  int y = 2;" in diff for diff in diffs)


def formatted_changed_lines(summary: dict, name: str) -> bool:
    """io.format formatted the edited line, left the committed line 1 as badly formatted as it was, and kept
    the BOM and every CRLF although the style names LF. Its own result names the lines it changed, so the
    formatting is io.format's and not the model's own new_string. The session's telemetry holds a line for
    each of the two io tool calls (task 38)."""
    changed = [each["lines"] for value in structured(summary) for each in value.get("files", ())]
    recorded = {line.get("tool") for line in summary["probe_log"] if line.get("event") == "tools/call"}
    return (summary["files"]["a.cpp"] == FORMATTED_CPP and any(changed)
            and recorded == {"io.edit", "io.format"})


def calls(name: str) -> list[dict]:
    """Each tool call of the newest run in order, with its turn counted from 0, whether its result was an
    error, and the result's text."""
    folder, _ = latest(name)
    made, answers, turn = [], {}, 0
    for line in (folder / "stream.jsonl").read_bytes().splitlines():
        message = json.loads(line) if line.startswith(b"{") else {}
        turn += message.get("type") == "result"
        if message.get("type") not in ("assistant", "user"):
            continue
        for block in (message.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use":
                made.append({"id": block.get("id"), "name": block.get("name"), "input": block.get("input"),
                             "turn": turn})
            elif block.get("type") == "tool_result":
                answers[block.get("tool_use_id")] = (bool(block.get("is_error")),
                                                     json.dumps(block.get("content")))
    for call in made:
        call["error"], call["text"] = answers.get(call["id"], (True, ""))
    return made


def no_op_left_alone(name: str) -> bool:
    """Claude Code refused an Edit that changes nothing, and io-guard added nothing about it."""
    refused = any(call["error"] and "No changes to make" in call["text"] for call in calls(name))
    return refused and not context_reached(name, "old_string and new_string")


def retries_after_refusals(name: str) -> dict[str, int | None]:
    """For each turn's code, the calls in that turn it took to get the job done after the refusal: those up to
    and including the first that ran without an error, lookups such as Read and Skill left out. None when
    the code refused nothing, and 0 when nothing after it ran."""
    made = calls(name)
    counts: dict[str, int | None] = {}
    for turn, code in enumerate(SKILL_REFUSALS):
        own = [call for call in made if call["turn"] == turn]
        first = next((index for index, call in enumerate(own) if call["error"] and code in call["text"]),
                     None)
        if first is None:
            counts[code] = None
            continue
        after = [call for call in own[first + 1:] if call["name"] not in LOOKUPS]
        ran = next((index for index, call in enumerate(after) if not call["error"]), None)
        counts[code] = 0 if ran is None else ran + 1
    return counts


def recovered_once(summary: dict, name: str) -> bool:
    """Each turn's command met its refusal, and the model's next call in that turn ran."""
    return all(tries == 1 for tries in retries_after_refusals(name).values())


def commit_asked(summary: dict, name: str) -> bool:
    """In auto mode, the ask rule put the git commit to the permission prompt, and the deny rule stopped
    git reset --hard with no prompt."""
    folder, _ = latest(name)
    permit = folder / "permit.jsonl"
    lines = permit.read_bytes().decode("utf-8").splitlines() if permit.is_file() else []
    prompted = "\n".join(line for line in lines if '"name": "probe_permit"' in line)
    denied = json.dumps((summary["final"] or {}).get("permission_denials") or [])
    return "git commit" in prompted and "reset --hard" not in prompted and "reset --hard" in denied


def commit_refused(summary: dict, name: str) -> bool:
    """The co-author commit met COMMIT_POLICY, and the commit that landed has no co-author line."""
    folder, _ = latest(name)
    log = subprocess.run(["git", "log", "--format=%B%x00"], cwd=folder / "work", capture_output=True,
                         check=True).stdout.decode("utf-8")
    landed = [message for message in log.split("\0") if message.strip()]
    return ("COMMIT_POLICY" in seen(summary) and len(landed) == 2
            and "co-authored-by" not in landed[0].lower())


def invisible_named(summary: dict, name: str) -> bool:
    """The Write put an invisible character inside line 2 of strip.py, U+FEFF as asked or another one a model
    picked instead, and the model read INVISIBLE_ADDED naming that character and line 2 (task 39)."""
    written = (summary["files"]["strip.py"] or "").encode("latin-1").decode("utf-8", "replace")
    line = written.split("\n")[1] if written.count("\n") >= 1 else ""
    found = [f"U+{ord(char):04X}" for char in line
             if ord(char) in (0xFEFF, 0xA0) or 0x2000 <= ord(char) <= 0x206F]
    return bool(found) and context_reached(name, f"INVISIBLE_ADDED: This Write added [{found[0]}] on line 2")


def results_shown(summary: dict, name: str) -> bool:
    """Both saved outputs came back as io-guard's view of them, and each shell.results line reached the
    model."""
    views = sum("[io-guard: the whole output is in" in str(result["content"])
                for result in summary["results"])
    return views == 2 and all(context_reached(name, needle) for needle in RESULTS_SEEN)


VERDICTS = {
    "rewrite-allow": lambda s, n: "IOPROBE_REWRITTEN" in seen(s),
    "write-bytes": lambda s, n: s["files"]["probe.txt"] == BOM_CRLF,
    "edit-extend": lambda s, n: s["files"]["edit.txt"] == "alpha BETA gamma\n",
    "read-context": lambda s, n: "IOPROBE-READ-CONTEXT" in seen(s),
    "failures": lambda s, n: logged(s, '"PostToolUseFailure", "tool_name": "Read"')
    and logged(s, '"PostToolUseFailure", "tool_name": "Bash"')
    and not logged(s, '"PostToolUseFailure", "tool_name": "Edit"'),
    "bash-diff-off": lambda s, n: not logged(s, "bashEditDiff"),
    "bash-diff-on": lambda s, n: logged(s, '"bashEditDiff": {"files"'),
    "env-file": lambda s, n: "export=env-file" in seen(s) and "plain=env-file" in seen(s),
    "updated-output": lambda s, n: "IOPROBE-UPDATED-OUTPUT" in seen(s),
    "time-exec": lambda s, n: len(s["hook_ms"]) >= 10,
    "time-shell": lambda s, n: len(s["hook_ms"]) >= 10,
    "hook-crash": lambda s, n: s["files"]["ran.txt"] is not None,
    "hook-timeout": lambda s, n: s["files"]["ran.txt"] is not None,
    "hook-badjson": lambda s, n: s["files"]["ran.txt"] is not None,
    "time-mcp": lambda s, n: sum('"gate_args"' in json.dumps(line) for line in s["probe_log"]) == 10,
    "mcp-gate": lambda s, n: s["files"]["gated.txt"] is None and "IOPROBE-MCP-DENY" in seen(s),
    "mcp-subst": lambda s, n: logged(s, '"number": "60000"') and logged(s, '"replace_all": "true"'),
    "ask-prompt": lambda s, n: logged(s, '"input": {"command": "echo IOPROBE_REWRITTEN"'),
    "auto-control": lambda s, n: debug_has(n, "Slow permission decision"),
    "auto-allow": lambda s, n: debug_has(n, "Hook approved tool use for Bash, bypassing permission prompt"),
    "era-legacy": lambda s, n: logged(s, '"received": {"method": "initialize"'),
    "era-auto": lambda s, n: logged(s, '"method": "server/discover"') and "DONE" in seen(s),
    "mcp-features": lambda s, n: "IOPROBE-ELICIT" in seen(s) and "IOPROBE-PROGRESS" in seen(s),
    "features-modern": lambda s, n: logged(s, '"inputResponses"'),
    "mcp-prompts": lambda s, n: every_call_denied(s),
    "mcp-permit": lambda s, n: sum('"name": "probe_permit"' in json.dumps(line)
                                   for line in s["probe_log"] if "received" in line) == 3,
    "dead-server": lambda s, n: s["files"]["second.txt"] is not None and logged(s, "die_after_gate reached"),
    "dead-for-good": lambda s, n: s["files"]["second.txt"] is not None and logged(s, "stays dead"),
    "guard-fields": lambda s, n: logged(s, '"tool_response": "{') and logged(s, '"error": "Exit code 3'),
    "guard-large": lambda s, n: large_arrived(s),
    "live-empty": lambda s, n: guarded_every_call(s) and s["files"]["w.txt"] is not None,
    "live-broken": lambda s, n: guarded_every_call(s) and s["files"]["w.txt"] is not None
    and logged(s, '"code": "GUARD_ERROR"') and context_reached(n, "IOGUARD-TEST-NOTE PostToolUse"),
    "live-answers": lambda s, n: "IOGUARD_REWRITTEN" in seen(s) and "IOGUARD_ALLOWED" in seen(s)
    and context_reached(n, "IOGUARD-TEST-NOTE PreToolUse Read")
    and context_reached(n, "IOGUARD-TEST-NOTE PostToolUse Read"),
    "live-refuse": lambda s, n: "Run this command instead" in seen(s) and "IOGUARD_REWRITTEN" in seen(s),
    "live-probe": defaults_applied,
    "live-move-ask": asked_with_moved_body,
    "live-move-auto": lambda s, n: "Run this command instead" in seen(s) and printed(s, "3"),
    "write-quiet": lambda s, n: s["files"]["probe.txt"] == BOM_CRLF and logged(s, '"name": "probe_permit"')
    and logged(s, "line one\\\\r\\\\nline two"),
    "live-read-profile": lambda s, n: context_reached(n, "io-guard: CRLF, BOM, UTF-8, tabs, 2 lines")
    and "CRLF, BOM" in seen(s),
    "edit-trailing": lambda s, n: s["files"]["one.txt"] == "one = \ntwo = 2\n",
    "live-conform": lambda s, n: s["files"]["keep.txt"] == KEPT_CONFORMED,
    "live-verify": lambda s, n: repaired_then_edited(s, n, ["Read", "Write", "Read", "Edit"]),
    "live-verify-direct": lambda s, n: repaired_then_edited(s, n, ["Read", "Write", "Edit"]),
    "live-read-only": lambda s, n: s["files"]["Hero.uasset"] == "hero v1\n"
    and "READ_ONLY: Hero.uasset is read-only. Lock it with git lfs lock Hero.uasset" in seen(s),
    "live-space-dropped": lambda s, n: s["files"]["ws.txt"] == SPACE_KEPT and "SPACE_DROPPED: " in seen(s),
    "live-locked": lambda s, n: s["files"]["keep.txt"] == "alpha\n"
    and context_reached(n, "FILE_LOCKED: Python (process"),
    "live-diagnose": lambda s, n: all(context_reached(n, needle) for needle in DIAGNOSED)
    and no_op_left_alone(n),
    "live-touched": lambda s, n: all(context_reached(n, needle) for needle in (
        "TOUCHED_BY_SHELL: This command changed a.cpp, read before it",
        "EOL_MISMATCH: This command changed conv.txt from CRLF to LF line endings.")),
    "live-results": results_shown,
    "live-pipe-once": piped_twice_warned_once,
    "live-verify-output": lambda s, n: context_reached(n, "VERIFY_OUTPUT: io-guard ran python -m py_compile"),
    "live-read-width": lambda s, n: context_reached(n, "io-guard: LF, UTF-8, 4 spaces, 7 lines"),
    "edit-delete-join": lambda s, n: s["files"]["f.txt"] == "ac\n",
    "live-lines-joined": lambda s, n: s["files"]["f.txt"] == "a\nc\n" and "LINES_JOINED: " in seen(s),
    "live-script-write": lambda s, n: s["files"]["a.txt"].replace("\r\n", "\n") == "two\n"
    and context_reached(n, "SHELL_WRITE: This command gives")
    and context_reached(n, "SHELL_WRITE: rewrite.py changed a.txt"),
    "live-touched-index": index_left_alone,
    "live-server": lambda s, n: served(s, n, "legacy"),
    "live-server-modern": lambda s, n: served(s, n, "modern"),
    "live-server-down": down_named,
    "live-edit-parallel": edits_interleaved,
    "live-run-body": body_ran,
    "live-run-background": ran_in_background,
    "live-run-denied": lambda s, n: "RULE_DENIED: io.run would run git push origin main" in seen(s),
    "live-run-asked": run_asked,
    "live-restore": restore_asked,
    "live-stage": staged_one_hunk,
    "live-format": formatted_changed_lines,
    "live-format-dry": dry_run_shown,
    "live-skill": recovered_once,
    "live-commit-asked": commit_asked,
    "live-invisible": invisible_named,
    "live-commit-policy": commit_refused,
    "live-skill-doctor": lambda s, n: "io-guard" in json.dumps(s["final"]),
    "command-output": lambda s, n: logged(s, '"error": "Exit code 1\\nIOPROBE_OUT\\nIOPROBE_ERR"')
    and sum("IOPROBE-SUMMARY" in str(result["content"]) and "persisted-output" not in str(result["content"])
            for result in s["results"]) == 3,
    "edit-refusals": lambda s, n: hooks_started(s, "Edit") == set() and all(
        text in seen(s) for text in ("File has not been read yet", "String to replace not found",
                                     "Found 2 matches", "No changes to make")),
    "other-refusals": lambda s, n: hooks_started(s, "Edit") | hooks_started(s, "Write") == set()
    and {"PostToolUseFailure:Read", "PostToolUseFailure:Grep", "PostToolUseFailure:Glob"}
    <= hooks_started(s, "Read") | hooks_started(s, "Grep") | hooks_started(s, "Glob"),
}


def verdict(name: str) -> str:
    folder, summary = latest(name)
    check = VERDICTS.get(name)
    outcome = "no verdict" if check is None else ("pass" if check(summary, name) else "FAIL")
    return f"{outcome:<10} {name:<16} claude {summary.get('claude')}  {folder.name}"


def print_json(value: dict) -> None:
    sys.stdout.buffer.write(json.dumps(value, indent=1).encode("ascii") + b"\n")


def main(argv: list[str]) -> int:
    match argv:
        case ["list"]:
            for name, probe in PROBES.items():
                print(f"{probe.item:>2} {name}")
        case ["run", *names] if names:
            with ThreadPoolExecutor(max_workers=4) as pool:
                checked = [name for name in PROBES if name in VERDICTS]
                for out in pool.map(run, checked if names == ["all"] else names):
                    print(out)
        case ["brief", *names] if names:
            for name in names:
                print_json(brief(name))
        case ["verdicts", *names]:
            for name in names or [name for name in PROBES if name in VERDICTS]:
                print(verdict(name))
        case ["timing", *names] if names:
            for name in names:
                print(timing(name) or f"{name}: no PreToolUse hook timed")
        case ["show", name]:
            folder, summary = latest(name)
            print_json(summary)
            print(folder)
        case ["assemble", name, folder]:
            root = Path(folder).resolve()
            assemble(name, PROBES[name], root / "plugins" / "io-probe", root / "probe.jsonl")
            write_json(root / ".claude-plugin" / "marketplace.json", {
                "name": "io-probe-local", "owner": {"name": "io-guard probes"},
                "plugins": [{"name": "io-probe", "source": "./plugins/io-probe"}]})
            print(root)
        case _:
            print(__doc__)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
