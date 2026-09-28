"""A Bash or PowerShell deny or ask rule meets an argument list the way Claude Code's rule meets a command, so
io.run is no way around it (D14)."""
import json
import unittest
from pathlib import Path

from ioguard.lib import rules
from ioguard.lib.platform import Platform

SOURCE = Path("C:/Users/u/.claude/settings.json")


def loaded(deny=(), ask=(), **extra) -> rules.Rules:
    settings = {"permissions": {"deny": list(deny), "ask": list(ask), **extra}}
    return rules.rules_in(json.dumps(settings).encode(), SOURCE)


def decision(rule: str, argv: list[str]) -> str:
    return rules.match_argv(loaded(deny=[rule]), argv).decision


class ARuleMeetsTheCommandItNames(unittest.TestCase):
    def test_the_documented_wildcard_rows(self):
        for rule, argv, met in (
                ("Bash(npm run build)", ["npm", "run", "build"], True),
                ("Bash(npm run build)", ["npm", "run", "build", "--watch"], False),
                ("Bash(npm run *)", ["npm", "run"], True),
                ("Bash(npm run *)", ["npm", "install"], False),
                ("Bash(git log * main)", ["git", "log", "-5", "main"], True),
                ("Bash(git log * main)", ["git", "log", "main"], False),
                ("Bash(* --version)", ["node", "--version"], True),
                ("Bash(ls *)", ["ls"], True),
                ("Bash(ls *)", ["lsof"], False),
                ("Bash(ls*)", ["lsof"], True),
                ("Bash(* --help *)", ["npm", "--help"], False),
                ("Bash(ls:*)", ["ls", "-la"], True),
                ("Bash(git:* push)", ["git", "push"], False),
                ("Bash", ["anything"], True), ("Bash(*)", ["anything"], True)):
            with self.subTest(rule=rule, argv=argv):
                self.assertEqual(decision(rule, argv) == "deny", met,
                                 "the rows of the permissions docs' wildcard table, on an argument list")

    def test_wrappers_assignments_and_the_programs_path_are_seen_through(self):
        for argv in (["timeout", "-s", "KILL", "30", "git", "push"], ["nohup", "git", "push", "origin"],
                     ["GIT_TRACE=1", "git", "push"], ["C:\\Program Files\\Git\\cmd\\git.exe", "push"],
                     ["xargs", "git", "push"]):
            with self.subTest(argv=argv):
                self.assertEqual(decision("Bash(git push *)", argv), "deny",
                                 "a wrapped command, or the program by its bare name, meets the rule")
        self.assertEqual(decision("Bash(git push *)", ["git", "-C", ".", "push"]), "none",
                         "a push written another way is not the command the rule names, as in Claude Code")

    def test_a_powershell_rule_ignores_case_and_a_bash_rule_does_not(self):
        self.assertEqual((decision("PowerShell(remove-item *)", ["Remove-Item", "x"]),
                          decision("Bash(Git push *)", ["git", "push"])), ("deny", "none"),
                         "PowerShell rules match without case, as Claude Code's do")

    def test_a_word_with_a_space_is_quoted(self):
        self.assertEqual(rules.command_text(["git", "commit", "-m", "a b"]), "git commit -m 'a b'",
                         "the argument list reads as the command a person would write")


class DenyOutranksAsk(unittest.TestCase):
    def test_deny_comes_first_and_names_its_rule(self):
        found = rules.match_argv(loaded(deny=["Bash(git push --force *)"], ask=["Bash(git push *)"]),
                                 ["git", "push", "--force", "origin"])
        self.assertEqual((found.decision, found.rule.text), ("deny", "Bash(git push --force *)"),
                         "a deny rule wins over an ask rule, and the match names the rule the user wrote")
        self.assertEqual(rules.match_argv(loaded(ask=["Bash(git push *)"]), ["git", "push"]).decision, "ask",
                         "an ask rule alone asks")

    def test_other_tools_parameters_and_broken_files_hold_no_rule(self):
        found = loaded(deny=["Read(./.env)", "Bash(run_in_background:true)", "mcp__x", "Bash(rm *)"])
        self.assertEqual([rule.text for rule in found.deny], ["Bash(rm *)"],
                         "only Bash and PowerShell command rules apply to io.run")
        self.assertEqual(rules.rules_in(b"{not json", SOURCE), rules.Rules(), "a broken file holds no rule")

    def test_managed_only_rules_leave_the_others_out(self):
        managed = rules.MANAGED["win32"]
        only = json.dumps({"permissions": {"deny": ["Bash(rm *)"], "allowManagedPermissionRulesOnly": True}})
        files = {managed: only.encode(), SOURCE: json.dumps({"permissions": {"deny": ["Bash(git push *)"]}})
                 .encode()}
        found = rules.load([managed, SOURCE], files.get)
        self.assertEqual([rule.text for rule in found.deny], ["Bash(rm *)"],
                         "allowManagedPermissionRulesOnly makes the managed file the only source")
        self.assertEqual(len(rules.load([SOURCE, managed], {SOURCE: only.encode()}.get).deny), 1,
                         "the switch counts in the managed file only")


class TheSettingsFilesAreClaudeCodes(unittest.TestCase):
    def test_the_user_project_local_and_managed_files(self):
        files = rules.settings_files({"USERPROFILE": "C:/Users/u"}, Path("C:/p"), Platform("win32", True))
        self.assertEqual([path.as_posix() for path in files],
                         ["C:/Program Files/ClaudeCode/managed-settings.json",
                          "C:/Users/u/.claude/settings.json", "C:/p/.claude/settings.json",
                          "C:/p/.claude/settings.local.json"],
                         "managed first, then the user's, then the project's two")
        moved = rules.settings_files({"CLAUDE_CONFIG_DIR": "D:/cfg"}, Path("C:/p"), Platform("darwin", True))
        self.assertEqual(moved[1].as_posix(), "D:/cfg/settings.json",
                         "CLAUDE_CONFIG_DIR moves the user's file")


if __name__ == "__main__":
    unittest.main()
