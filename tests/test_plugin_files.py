"""The marketplace, the plugin manifest, the hooks and the server config agree with each other."""
import json
import re
import unittest

from ioguard.checks import restore_ask, run_rules, trust_ask
from ioguard.mcp.server import registry
from tests import PLUGIN_SCRIPTS, REPO

PLUGIN = REPO / "plugins" / "io-guard"


def load(path) -> dict:
    return json.loads(path.read_bytes())


class PluginFilesAgree(unittest.TestCase):
    def test_the_marketplace_entry_and_the_manifest_share_one_name(self):
        entry = load(REPO / ".claude-plugin" / "marketplace.json")["plugins"][0]["name"]
        self.assertEqual(entry, load(PLUGIN / ".claude-plugin" / "plugin.json")["name"],
                         "an install by the manifest name fails when the two names differ")

    def test_every_mcp_tool_hook_names_the_plugins_own_server(self):
        name = load(PLUGIN / ".claude-plugin" / "plugin.json")["name"]
        servers = {f"plugin:{name}:{key}" for key in load(PLUGIN / ".mcp.json")["mcpServers"]}
        hooks = load(PLUGIN / "hooks" / "hooks.json")["hooks"]
        named = {hook["server"] for groups in hooks.values() for group in groups for hook in group["hooks"]
                 if hook["type"] == "mcp_tool"}
        self.assertTrue(named, "hooks.json has at least one mcp_tool hook")
        self.assertLessEqual(named, servers, "an mcp_tool hook names plugin:<plugin>:<server> from .mcp.json")

    def test_every_io_tool_a_check_asks_about_reaches_the_pretooluse_hook(self):
        groups = load(PLUGIN / "hooks" / "hooks.json")["hooks"]["PreToolUse"]
        matcher = next(group["matcher"] for group in groups)
        missing = [name for name in (run_rules.RUN, restore_ask.RESTORE, trust_ask.TRUST, trust_ask.CONFIG)
                   if name not in matcher.split("|")]
        self.assertEqual(missing, [], "a check that answers ask on an io tool never runs unless the hook "
                                      "matches that tool")

    def test_the_server_and_the_command_hooks_start_python_through_pyrun(self):
        server = load(PLUGIN / ".mcp.json")["mcpServers"]["io"]
        self.assertEqual(server["command"], "${CLAUDE_PLUGIN_ROOT}/scripts/pyrun",
                         "the server's command is one file in the plugin, with no other variable (D29)")
        hooks = load(PLUGIN / "hooks" / "hooks.json")["hooks"]
        commands = [hook["command"] for groups in hooks.values() for group in groups
                    for hook in group["hooks"] if hook["type"] == "command"]
        self.assertTrue(commands, "hooks.json has command hooks")
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(command.startswith('sh "${CLAUDE_PLUGIN_ROOT}/scripts/pyrun" '),
                                "every command hook starts Python through pyrun")

    def test_the_manifest_asks_the_user_for_nothing(self):
        self.assertNotIn("userConfig", load(PLUGIN / ".claude-plugin" / "plugin.json"),
                         "a saved option is lost when the desktop renames the plugin, so IOGUARD_PYTHON "
                         "names Python instead (D29)")

    def test_every_script_a_hook_or_the_server_names_exists(self):
        texts = "".join(path.read_bytes().decode("utf-8")
                        for path in (PLUGIN / "hooks" / "hooks.json", PLUGIN / ".mcp.json"))
        for script in ("pyrun", "hook.py", "ioguard_mcp.py"):
            with self.subTest(script=script):
                self.assertIn(f"/scripts/{script}", texts, f"the plugin config starts {script}")
                self.assertTrue((PLUGIN_SCRIPTS / script).is_file(), f"scripts/{script} exists")
        self.assertTrue((PLUGIN_SCRIPTS / "pyrun.cmd").is_file(), "scripts/pyrun.cmd exists for cmd.exe")

    def test_every_skill_is_named_for_its_folder_and_names_only_tools_the_server_has(self):
        offered = {name.replace(".", "_") for name in registry().specs}
        for page in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
            text = page.read_bytes().decode("ascii")
            head = dict(line.split(": ", 1) for line in text.split("---")[1].strip().splitlines())
            named = set(re.findall(r"mcp__plugin_io-guard_io__(\w+)", text))
            with self.subTest(skill=page.parent.name):
                self.assertEqual((head.get("name"), bool(head.get("description")), named - offered),
                                 (page.parent.name, True, set()),
                                 "the plugin menu lists it by name, and every tool it names exists")

    def test_the_plugin_has_no_top_level_bin_folder(self):
        self.assertFalse((PLUGIN / "bin").exists(),
                         "a top-level bin/ makes Chat and Cowork refuse the whole plugin")


if __name__ == "__main__":
    unittest.main()
