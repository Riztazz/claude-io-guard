"""A Bash or PowerShell deny or ask rule meets an argument list the way Claude Code's rule meets a command, so
io.run is no way around it (D14)."""
import base64
import json
import unittest
from pathlib import Path

from ioguard.lib import rules
from ioguard.lib.platform import Platform

ENCODED_PUSH = base64.b64encode("git push".encode("utf-16-le")).decode("ascii")
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


class AShellStringIsReadAsTheCommandsItRuns(unittest.TestCase):
    def test_each_shell_given_a_string_names_it(self):
        cases = {("bash", "-c", "git push"): ("bash -c", "git push"),
                 ("C:/Git/bin/bash.exe", "-lc", "git push"): ("bash -lc", "git push"),
                 ("bash", "-o", "pipefail", "-c", "ls"): ("bash -c", "ls"),
                 ("pwsh", "-NoProfile", "-Command", "git", "push"): ("pwsh -Command", "git push"),
                 ("powershell", "-ExecutionPolicy", "Bypass", "git push"): ("powershell with a command",
                                                                            "git push")}
        for argv, (what, text) in cases.items():
            with self.subTest(argv=argv):
                found = rules.wrapped(argv)
                self.assertEqual(found.text, text, "the string the shell runs is read")
                self.assertTrue(found.what.startswith(what.split()[0]), "and named by its shell")

    def test_a_script_file_or_a_plain_program_is_not_a_string(self):
        for argv in (("bash", "build.sh", "-c"), ("pwsh", "-File", "x.ps1"), ("pwsh", "x.ps1"),
                     ("git", "push"), ("python", "tool.py", "-c")):
            with self.subTest(argv=argv):
                self.assertIsNone(rules.wrapped(argv),
                                  "a file or a program's own flag is not a command string")

    def test_code_strings_a_broken_encoded_command_and_cmd_are_unread(self):
        for argv in (("python3.12", "-c", "import os"), ("node", "-e", "1"), ("pwsh", "-enc", "not base64!"),
                     ("cmd", "/c", "git push"), ("perl", "-e", "1")):
            with self.subTest(argv=argv):
                found = rules.wrapped(argv)
                self.assertEqual((found is not None, found.text), (True, None),
                                 "io-guard names a code string it cannot read")

    def test_a_rule_meets_a_command_inside_the_string_at_any_depth(self):
        found = loaded(deny=["Bash(git push *)"], ask=["Bash(git fetch *)"])
        cases = {("bash", "-c", "git push origin"): "deny",
                 ("bash", "-c", "echo hi && git push"): "deny",
                 ("bash", "-c", "bash -c 'git push'"): "deny",
                 ("pwsh", "-Command", "& git push origin"): "deny",
                 ("sh", "-c", "git fetch"): "ask",
                 ("bash", "-c", "ls -la"): "none",
                 ("bash", "-c", "echo $(git push)"): "unread",
                 ("bash", "-c", "eval \"git $X\""): "unread",
                 ("bash", "-c", "eval \"$X\""): "none",
                 ("python", "-c", "import subprocess; subprocess.run(['git', 'push'])"): "unread",
                 ("python", "-c", "import subprocess"): "none",
                 ("pwsh", "-EncodedCommand", ENCODED_PUSH): "deny",
                 ("git", "push"): "deny"}
        for argv, decision in cases.items():
            with self.subTest(argv=argv):
                self.assertEqual(rules.match_command(found, argv).decision, decision,
                                 "a wrapped command meets the rules as if it ran on its own")

    def test_a_command_spelled_the_way_only_the_shell_reads_it_meets_the_rule(self):
        found = loaded(deny=["Bash(git push *)", "PowerShell(git push *)"])
        cases = {("bash", "-c", "git \\\npush origin"): "a backslash before a newline joins the lines",
                 ("bash", "-c", "gi\\\nt push origin"): "even inside a word",
                 ("bash", "-c", "(( 1 << 2 ))\ngit push origin"): "<< inside (( )) is a shift",
                 ("bash", "-c", "for (( i = 1 << 2; i < 9; i++ )); do git push origin; done"): "and in a for",
                 ("bash", "-c", "cat <<$'EOF'\nx\nEOF\ngit push origin"): "a $'...' delimiter is EOF",
                 ("pwsh", "-Command", "& { git push }"): "a script block runs its commands",
                 ("pwsh", "-Command", "if ($true) { git push }"): "so does an if body",
                 ("pwsh", "-Command", "1 | ForEach-Object { git push }"): "and a ForEach-Object block"}
        for argv, why in cases.items():
            with self.subTest(argv=argv):
                self.assertEqual(rules.match_command(found, argv).decision, "deny", why)

    def test_a_powershell_expression_runs_nothing_and_an_assignment_runs_its_command(self):
        found = loaded(deny=["PowerShell(git push *)"])
        cases = {"git status | ForEach-Object { $_.Line }": "none",
                 "$count = 3; git status": "none",
                 "$out = git push origin": "deny",
                 "$out = & git push origin": "deny",
                 "$tool = 'git'; & $tool push": "unread",
                 "git log; & ($name) push": "unread"}
        for text, decision in cases.items():
            with self.subTest(text=text):
                self.assertEqual(rules.match_command(found, ("pwsh", "-Command", text)).decision, decision,
                                 "a statement that starts with a variable is an expression or an assignment, "
                                 "and only & or . calls through one")

    def test_a_heredoc_that_never_ends_leaves_the_string_unread(self):
        found = loaded(deny=["Bash(git push *)"])
        argv = ("bash", "-c", "cat <<EOF\nx\ngit push origin")
        self.assertEqual(rules.match_command(found, argv).decision, "unread",
                         "a heredoc io-guard finds no end of may end where bash reads one, so the string is "
                         "unread")

    def test_a_rules_program_is_named_only_as_a_whole_word(self):
        found = loaded(deny=["Bash(git push *)"], ask=["PowerShell(Remove-Item:*)"])
        cases = {"subprocess.run(['git', 'push'])": "Bash(git push *)", "x = 'legit'": None,
                 "git-lfs pull": None, "remove-item x": "PowerShell(Remove-Item:*)"}
        for text, rule in cases.items():
            with self.subTest(text=text):
                named = rules.rule_named(found, text)
                self.assertEqual(named.text if named else None, rule, "a program counts only as a word")
        self.assertEqual(rules.rule_named(loaded(ask=["Bash"]), "print(1)").text, "Bash",
                         "a bare rule meets every command, so it names every text")

    def test_nesting_past_the_limit_is_unread(self):
        argv = ["git", "status"]
        for _ in range(rules.NESTED + 1):
            argv = ["bash", "-c", rules.command_text(argv)]
        self.assertEqual(rules.match_command(loaded(deny=["Bash(git push *)"]), argv).decision, "unread",
                         "a string nested past NESTED shells is not followed")


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
