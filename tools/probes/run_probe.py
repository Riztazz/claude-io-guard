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

A live-* probe runs io-guard itself from plugins/io-guard instead of a one-off plugin, with its python option
set through --settings and tests/support/inject on PYTHONPATH, so the test checks its guard field names run in
the hook and the server as shipped. Its log is the session's io-guard telemetry. The guard-* probes point the
one-off plugin's hooks at io-guard's own hooks.json maps, to record what they receive.
"""
import json
import os
import re
import shutil
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
GUARD_DATA = Path.home() / ".claude" / "plugins" / "data" / "io-guard-inline"
GUARD_INPUTS = {event: groups[0]["hooks"][0].get("input") for event, groups in
                json.loads((GUARD / "hooks" / "hooks.json").read_bytes())["hooks"].items()}
INJECT = REPO / "tests" / "support" / "inject"
HOOK_SH = (GUARD / "scripts" / "hook.sh").as_posix()
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
    "launch-hooksh": Probe(0, "record", hooks=(("PreToolUse", "Bash", "hooksh"),), allowed=("Bash",),
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
        case "hooksh":
            entry = {"type": "command", "command": f'sh "{HOOK_SH}" pre_tool_use'}
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
        (work / rel).write_bytes(data)
    if probe.extra.get("outside_dir"):
        (work.parent / "outside").mkdir()
        (work.parent / "outside" / "keep.txt").write_bytes(b"keep\n")
    if not probe.git:
        return
    identity = ("-c", "user.name=io-probe", "-c", "user.email=probe@localhost")
    git(work, "init", "-q", "-b", "main")
    git(work, *identity, "add", "-A")
    git(work, *identity, "commit", "-q", "-m", "probe")


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
    """The settings and environment that run io-guard from this checkout with the probe's test checks: the
    python option the server starts from, and tests/support/inject on PYTHONPATH."""
    options = {"pluginConfigs": {"io-guard@inline": {"options": {"python": str(PYTHON)}}}}
    env = {"PYTHONPATH": str(INJECT), "IOGUARD_TEST_CHECKS": probe.guard}
    return {**(probe.settings or {}), **options}, env


def copy_telemetry(lines: list[bytes], log: Path) -> None:
    """io-guard's telemetry for the session the stream names, as the run's log."""
    for line in lines:
        message = json.loads(line) if line.startswith(b"{") else {}
        if message.get("type") == "system" and message.get("subtype") == "init":
            found = sorted(GUARD_DATA.glob(f"events/*/{message.get('session_id')}.jsonl"))
            if found:
                shutil.copyfile(found[-1], log)
            return


def run(name: str) -> Path:
    probe = PROBES[name]
    out = OUT / name / time.strftime("%Y%m%d-%H%M%S")
    plugin, work, log = out / "plugin", out / "work", out / "probe.jsonl"
    settings, env = probe.settings, probe.env
    if probe.guard is None:
        assemble(name, probe, plugin, log)
    else:
        plugin = GUARD
        settings, extra = guarded(probe)
        env = {**env, **extra}
    prepare_work(probe, work)
    claude = os.environ.get("IOPROBE_CLAUDE", "claude")
    argv = [claude, "-p", probe.prompt, "--plugin-dir", str(plugin), "--output-format", "stream-json",
            "--verbose", "--include-hook-events", "--debug-file", str(out / "debug.txt"),
            "--permission-mode", probe.permission, "--model", probe.model,
            "--max-turns", str(probe.max_turns), *probe.extra_args]
    if probe.allowed:
        argv += ["--allowedTools", *probe.allowed]
    if settings is not None:
        argv += ["--settings", json.dumps(settings)]
    started = time.time()
    lines, arrivals = [], []
    with (out / "stderr.txt").open("wb") as stderr:
        session = subprocess.Popen(argv, cwd=work, stdout=subprocess.PIPE, stderr=stderr,
                                   env={**os.environ, **env})
        killer = threading.Timer(600, session.kill)
        killer.start()
        for line in session.stdout:
            arrivals.append(time.time_ns())
            lines.append(line)
        exit_code = session.wait()
        killer.cancel()
    (out / "stream.jsonl").write_bytes(b"".join(lines))
    if probe.guard is not None:
        copy_telemetry(lines, log)
        if (GUARD_DATA / "probe.json").is_file():
            shutil.copyfile(GUARD_DATA / "probe.json", out / "guard-probe.json")
    details = summarise(out / "stream.jsonl", log, work, probe)
    versions = [note["version"] for note in details["notes"] if isinstance(note, dict) and "version" in note]
    summary = {"probe": name, "item": probe.item, "claude": versions[0] if versions else None,
               "exit": exit_code, "seconds": round(time.time() - started, 1),
               "hook_ms": hook_durations(lines, arrivals), **details}
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
    folder, _ = latest(name)
    project = Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(folder / "work"))
    for path in project.glob("*.jsonl"):
        for line in path.read_bytes().splitlines():
            attachment = json.loads(line).get("attachment") or {}
            if attachment.get("type") == "hook_additional_context" and needle in json.dumps(attachment):
                return True
    return False


def defaults_applied(summary: dict, name: str) -> bool:
    """The arrow printed through Bash, the same command without the defaults failed, and the session probe
    named the Claude Code version."""
    folder, _ = latest(name)
    saved = folder / "guard-probe.json"
    probe = json.loads(saved.read_bytes()) if saved.is_file() else {}
    outputs = [str(result["content"]) for result in summary["results"]]
    return (len(outputs) >= 2 and chr(0x2192) in outputs[0] and "UnicodeEncodeError" in outputs[1]
            and probe.get("claude_code_version") is not None)


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
