"""The marketplace, the plugin manifest, the hooks and the server config agree with each other."""
import json
import unittest

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

    def test_the_server_starts_from_the_python_setting(self):
        server = load(PLUGIN / ".mcp.json")["mcpServers"]["io"]
        self.assertEqual(server["command"], "${user_config.python}",
                         "the io server starts from the interpreter the user set (D15)")
        self.assertIn("python", load(PLUGIN / ".claude-plugin" / "plugin.json")["userConfig"],
                      "the manifest declares the python setting the server starts from")

    def test_every_script_a_hook_or_the_server_names_exists(self):
        texts = "".join(path.read_bytes().decode("utf-8")
                        for path in (PLUGIN / "hooks" / "hooks.json", PLUGIN / ".mcp.json"))
        for script in ("hook.sh", "server.py"):
            with self.subTest(script=script):
                self.assertIn(f"/scripts/{script}", texts, f"the plugin config starts {script}")
                self.assertTrue((PLUGIN_SCRIPTS / script).is_file(), f"scripts/{script} exists")

    def test_the_plugin_has_no_top_level_bin_folder(self):
        self.assertFalse((PLUGIN / "bin").exists(),
                         "a top-level bin/ makes Chat and Cowork refuse the whole plugin")


if __name__ == "__main__":
    unittest.main()
