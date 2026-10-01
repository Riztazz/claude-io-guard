"""kills.broad_stop finds a stop that reaches other sessions' processes: by a shared runtime's name, or by a
command-line match. A stop by id, by port, or by one application's name is left alone."""
import unittest

from ioguard.lib import kills, pwsh, shell

LISTING = "every process a Win32_Process match picks"
POWERSHELL = {
    "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | Where-Object { $_.CommandLine -match "
    "\"server.py\" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }": LISTING,
    "Stop-Process -Name python -Force": "every python process",
    "Stop-Process -Name 'node','python' -Force": "every node process",
    "Get-Process python | Stop-Process": "every python process",
    "taskkill /F /IM python.exe": "every python.exe process",
    "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { $_.CommandLine -match "
    "'http.server' } | ForEach-Object { Stop-Process -Id $_.ProcessId }": LISTING,
    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'UnrealBuildTool' } | "
    "ForEach-Object { Stop-Process -Id $_.ProcessId }": LISTING,
    "Get-CimInstance Win32_Process -Filter \"Name like 'UnrealEditor%'\" | Where-Object { "
    "$_.CommandLine -like '*Game.uproject*' } | ForEach-Object { Stop-Process -Id $_.ProcessId }": None,
    "Stop-Process -Name UnrealEditor -Force": None,
    "Get-Process -Name UnrealEditor* | Stop-Process -Force": None,
    "taskkill /F /IM UnrealEditor.exe": None,
    "$conn = Get-NetTCPConnection -LocalPort 8420; Stop-Process -Id $conn[0].OwningProcess -Force": None,
    "Stop-Process -Id 25300 -Force": None,
    "Get-Process -Id 25300 | Stop-Process": None,
    "Stop-Process -Id 33896 -Force; Get-Process LiveCodingConsole | Measure-Object": None,
    "Stop-Process -Id 40564 -Force; Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | "
    "Select-Object ProcessId": None,
    "Get-Process python": None,
    "Get-Process | Where-Object {$_.ProcessName -eq 'python'} | Stop-Process -Force": "every python process",
    "Get-Process | ? { $_.Path -like '*node*' } | kill": "every node process",
    "Get-Process | Where-Object { $_.Id -eq 25300 } | Stop-Process": None,
    "Write-Output 'Stop-Process -Name python'": None,
    "Get-CimInstance Win32_Process | Select-Object Name": None,
}
BASH = {
    "pkill -f server.py": "every process pkill -f matches",
    "pkill node": "every node process",
    "kill $(pgrep -f server.py)": "every process a pgrep match picks",
    "ps aux | grep server.py | awk '{print $2}' | xargs kill": "every process a ps aux match picks",
    "taskkill //F //IM python.exe": "every python.exe process",
    "taskkill //F //FI \"IMAGENAME eq node.exe\"": "every process taskkill /FI matches",
    "wmic process where \"name='node.exe'\" delete": "every process wmic matches",
    "killall node": "every node process",
    "killall Xcode": None,
    "pkill -F run.pid": None,
    "taskkill //F //IM UnrealEditor.exe": None,
    "kill 1234": None,
    "echo 'pkill -f x'": None,
    "ps aux | grep node": None,
    "pgrep -f server.py": None,
    "git log --grep=pkill": None,
}


CLAIM = "a runtime's name or a command-line match is found, and an id, a port or one app is not"


class AStopThatReachesOtherSessionsIsFound(unittest.TestCase):
    def test_each_powershell_shape(self):
        for command, expected in POWERSHELL.items():
            with self.subTest(command=command):
                self.assertEqual(kills.broad_stop(command, pwsh.blanked(command)), expected, CLAIM)

    def test_each_bash_shape(self):
        for command, expected in BASH.items():
            with self.subTest(command=command):
                self.assertEqual(kills.broad_stop(command, shell.blanked(command)), expected, CLAIM)


if __name__ == "__main__":
    unittest.main()
