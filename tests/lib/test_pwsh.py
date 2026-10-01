"""lib.pwsh splits a PowerShell command into simple commands, and finds its file redirects and [IO.File]
calls."""
import threading
import unittest

from ioguard.lib import pwsh


class PowerShellCommands(unittest.TestCase):
    def test_commands_split_at_pipes_semicolons_and_chains(self):
        found = pwsh.commands("Get-Item 'a;b' | Select-Object -First 1; git status && echo 'it''s'")
        self.assertEqual([command.words for command in found],
                         [("Get-Item", "a;b"), ("Select-Object", "-First", "1"), ("git", "status"),
                          ("echo", "it's")], "quotes keep their separators, and '' is one quote")

    def test_a_stray_closing_bracket_is_passed_over_and_never_stops_the_parse(self):
        shapes = {"Write-Host 'x' }": [("Write-Host", "x")], "echo a)": [("echo", "a")],
                  "echo a ]": [("echo", "a")], "(echo a) )": [("(echo a)",)],
                  "Get-ChildItem | % { $_.Name } }": [("Get-ChildItem",), ("%", "{ $_.Name }")],
                  "echo a > )": [("echo", "a")]}
        found: dict[str, list] = {}

        def parse() -> None:
            for command in shapes:
                found[command] = [each.words for each in pwsh.commands(command)]
        worker = threading.Thread(target=parse, daemon=True)
        worker.start()
        worker.join(5)
        self.assertEqual((worker.is_alive(), found), (False, shapes),
                         "a ), ] or } that closes nothing is skipped, and the parse ends")

    def test_a_call_operator_is_not_the_program(self):
        found = pwsh.commands('& "C:\\tools\\x.exe" -a > out.txt; . ./setup.ps1')
        self.assertEqual([each.name for each in found], ["x", "setup.ps1"],
                         "& and . run the word after them, which is the program")

    def test_a_here_string_is_one_word(self):
        found = pwsh.commands("git commit -m @'\nfirst | line; two\n'@ 2>&1 | Select-Object -Last 6")
        self.assertEqual([command.name for command in found], ["git", "select-object"],
                         "the here-string's text holds no separator")
        self.assertEqual(found[0].redirects, (), "2>&1 duplicates a stream and names no file")

    def test_file_redirects_keep_their_stream(self):
        found = pwsh.commands("Get-Date > now.txt; Write-Error x 2>> err.txt; Get-Date *> all.txt")
        redirects = [command.redirects[0] for command in found]
        self.assertEqual([(redirect.target, redirect.append, redirect.fd) for redirect in redirects],
                         [("now.txt", False, 1), ("err.txt", True, 2), ("all.txt", False, None)],
                         "each redirect names its file, its stream and whether it appends")

    def test_a_comment_holds_no_command(self):
        found = pwsh.commands("# Set-Content x y\n<# Out-File z #>\nGet-Date")
        self.assertEqual(found[0].words, ("Get-Date",), "line and block comments are skipped")

    def test_blanked_code_keeps_no_string_or_comment(self):
        command = "$a = 'x $pid = 1' # $home = 2\n$b = @\"\n$host = 3\n\"@\n$c = 4"
        blanked = pwsh.blanked(command)
        self.assertEqual((len(blanked), blanked.count("\n"), "$pid" in blanked, "$c = 4" in blanked),
                         (len(command), command.count("\n"), False, True),
                         "strings, here-strings and comments turn to spaces, and the code and offsets stay")

    def test_io_file_calls_name_their_path(self):
        found = pwsh.file_calls("[System.IO.File]::WriteAllText(\"C:/p/a.txt\", $x)")
        self.assertEqual(found, ("C:/p/a.txt",), "the literal path of a write call is found")

    def test_a_script_block_is_found_outside_strings_and_comments(self):
        command = "'{no}' | ForEach-Object { if ($_) { git push } } # {not}\n& { ls }"
        self.assertEqual(pwsh.script_blocks(command), (" if ($_) { git push } ", " ls "),
                         "each outermost block, with a brace in a string or a comment left out")


if __name__ == "__main__":
    unittest.main()
