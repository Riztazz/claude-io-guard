#!/bin/sh
# Starts an io-guard command hook with a Python that runs on this machine: sh hook.sh <event>, with the
# hook event as JSON on stdin, which hook.py reads. It runs under Git Bash on Windows and sh on macOS, and
# uses only shell builtins, so it works with any PATH. The interpreter the user set, then python3, python and
# py -3 are tried in turn, and a path under WindowsApps is skipped, because that is the Microsoft Store stub.
# With no interpreter found, the answer is a systemMessage naming the fix, and the exit code is 0.

event="$1"
here="${0%[/\\]*}"
[ "$here" = "$0" ] && here=.

for candidate in "${CLAUDE_PLUGIN_OPTION_PYTHON:-}" python3 python; do
    [ -n "$candidate" ] || continue
    found=$(command -v "$candidate" 2>/dev/null) || continue
    case "$found" in
        *WindowsApps*) continue ;;
    esac
    exec "$candidate" "$here/hook.py" "$event"
done

if command -v py >/dev/null 2>&1; then
    exec py -3 "$here/hook.py" "$event"
fi

what='io-guard found no Python on this machine, so it checks nothing this session.'
fix='Install Python 3.14 or later, then set the interpreter with /plugin configure io-guard.'
printf '{"systemMessage": "%s %s"}\n' "$what" "$fix"
exit 0
