#!/usr/bin/env python3
"""One-click dashboard opener - works the same on Windows, Linux, and macOS.

Usage:
    python open_dashboard.py path/to/session.jsonl
    (or run with no argument and it will prompt for the path)

On Windows this also works by dragging a .jsonl file onto this script
in File Explorer (if .py files are associated with Python), or by
double-clicking it and pasting the path when prompted.

Builds the markdown + HTML report next to this script and opens the
dashboard in your default browser. Uses only the Python standard
library plus this repo's own mr_d_sniffer package - no pip installs
needed, and no need to figure out whether "python" or "python3" is on
PATH since you're already running this with whichever one you have.
"""

import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mr_d_sniffer.report import write_html_report, write_report  # noqa: E402


def main() -> int:
    log_path = sys.argv[1] if len(sys.argv) > 1 else input("Path to .jsonl session log: ")
    log_path = log_path.strip().strip('"').strip("'")

    if not os.path.isfile(log_path):
        print(f"Could not find: {log_path}", file=sys.stderr)
        return 1

    base_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(base_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    basename = os.path.splitext(os.path.basename(log_path))[0]
    md_path = os.path.join(reports_dir, f"{basename}.md")
    html_path = os.path.join(reports_dir, f"{basename}.html")

    print(f"Building dashboard from {log_path} ...")
    write_report(log_path, md_path)
    write_html_report(log_path, html_path)

    print(f"Done. Dashboard: {html_path}")
    webbrowser.open(f"file://{os.path.abspath(html_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
