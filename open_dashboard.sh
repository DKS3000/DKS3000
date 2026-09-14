#!/usr/bin/env bash
# One-click dashboard opener for Linux/macOS.
#
# Usage:
#   ./open_dashboard.sh path/to/session.jsonl
#   (or run with no argument and it will prompt for the path)
#
# Builds the markdown + HTML report next to this script and opens the
# dashboard in your default browser. Report generation uses only the
# standard library, so any Python 3 install works.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

LOGFILE="${1:-}"
if [ -z "$LOGFILE" ]; then
    read -rp "Path to .jsonl session log: " LOGFILE
fi

# Strip any surrounding quotes the user may have pasted.
LOGFILE="${LOGFILE%\"}"
LOGFILE="${LOGFILE#\"}"

if [ ! -f "$LOGFILE" ]; then
    echo "Could not find: $LOGFILE" >&2
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    PYCMD=python3
elif command -v python >/dev/null 2>&1; then
    PYCMD=python
else
    echo "Python 3 was not found on PATH. Install it and try again." >&2
    exit 1
fi

mkdir -p reports
BASENAME="$(basename "$LOGFILE")"
BASENAME="${BASENAME%.*}"

echo "Building dashboard from $LOGFILE ..."
"$PYCMD" -m rf_sniffer report --log "$LOGFILE" \
    --out "reports/${BASENAME}.md" --html "reports/${BASENAME}.html" --open

echo "Done. Dashboard: reports/${BASENAME}.html"

if ! "$PYCMD" -c "import webbrowser,sys; sys.exit(0 if webbrowser.get() else 1)" >/dev/null 2>&1; then
    echo "(No browser launcher detected in this environment - e.g. headless SSH session.)"
    echo "Copy reports/${BASENAME}.html to a machine with a browser, or serve it:"
    echo "  python3 -m http.server 8000 --directory reports"
fi
