"""A command hook that records every event it receives, then answers as the probe's mode says.

argv[1] names the hook form, exec or shell, so the log tells the two apart. The probe's settings are in
probe.json at the plugin root: the mode, the nonce and the log path.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import answers  # noqa: E402

ENV_KEYS = ("CLAUDE_ENV_FILE", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "CLAUDE_PROJECT_DIR",
            "CLAUDE_EFFORT", "CLAUDE_CODE_ENTRYPOINT", "MCP_PROTOCOL_NEGOTIATION", "MCP_SDK_GENERATION")


def record(log: Path, line: dict) -> None:
    with log.open("ab") as out:
        out.write((json.dumps(line) + "\n").encode("ascii"))


def write_env_file(nonce: str) -> str | None:
    target = os.environ.get("CLAUDE_ENV_FILE")
    if not target:
        return None
    lines = f"export IOPROBE_ENV_EXPORT={nonce}\nIOPROBE_ENV_PLAIN={nonce}\n"
    with open(target, "ab") as out:
        out.write(lines.encode("ascii"))
    return target


def main() -> int:
    started_ns = time.time_ns()
    probe = json.loads((ROOT / "probe.json").read_bytes())
    raw = sys.stdin.buffer.read()
    try:
        event = json.loads(raw)
    except ValueError:
        event = {"unparsed": raw.decode("utf-8", "replace")}
    mode, nonce = probe["mode"], probe["nonce"]
    name = event.get("hook_event_name")
    env = {key: os.environ.get(key) for key in ENV_KEYS}
    env.update({key: value for key, value in os.environ.items() if key.startswith("CLAUDE_PLUGIN_OPTION_")})
    line = {"source": "hook", "form": sys.argv[1] if len(sys.argv) > 1 else None, "started_ns": started_ns,
            "pid": os.getpid(), "mode": mode, "event": event, "env": env}

    if name == "SessionStart" and mode == "envfile":
        line["env_file_written"] = write_env_file(nonce)
    reply = answers.answer(mode, event, nonce)
    line["answer"] = reply
    line["finished_ns"] = time.time_ns()
    record(Path(probe["log"]), line)

    if name == "PreToolUse" and event.get("tool_name") == "Bash":
        match mode:
            case "crash":
                raise RuntimeError(f"io-probe crashes on purpose ({nonce})")
            case "timeout":
                time.sleep(probe.get("sleep_s", 10))
            case "badjson":
                sys.stdout.buffer.write(b"{io-probe: this is not json}")
                return 0
    if reply is not None:
        sys.stdout.buffer.write(json.dumps(reply).encode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
