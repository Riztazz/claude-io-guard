@echo off
rem pyrun for cmd.exe: pyrun.cmd <script> [arguments]. On Windows the io server's command, scripts/pyrun,
rem resolves to this file. IOGUARD_PYTHON names the interpreter. Without it, py -3 runs, the launcher
rem python.org installs, then python. A command is looked up on PATH only, never in the project folder
rem the server starts in. Nothing here writes to stdout, which carries the server's messages.
setlocal
set NoDefaultCurrentDirectoryInExePath=1
if not defined IOGUARD_PYTHON goto search
if exist "%IOGUARD_PYTHON%" goto named
where /q "$PATH:%IOGUARD_PYTHON%" 2>nul && goto named
1>&2 echo io-guard: IOGUARD_PYTHON is %IOGUARD_PYTHON%, which is not a program. Set it to the full path of Python 3.14 or later.
exit /b 1

:search
where /q $PATH:py 2>nul && goto launcher
where /q $PATH:python 2>nul && goto plain
1>&2 echo io-guard found no Python. Install Python 3.14 or later, or set IOGUARD_PYTHON to its full path.
exit /b 1

:named
"%IOGUARD_PYTHON%" %*
exit /b %errorlevel%

:launcher
py -3 %*
exit /b %errorlevel%

:plain
python %*
exit /b %errorlevel%
