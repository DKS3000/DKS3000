"""Command-line entry point for the RF recon sniffer.

Usage:
    python -m rf_sniffer wifi --iface wlan1mon --out logs/ --duration 300
    python -m rf_sniffer ble --out logs/ --duration 300
    python -m rf_sniffer both --iface wlan1mon --out logs/ --duration 300
    python -m rf_sniffer report --log logs/wifi_20260101T000000Z.jsonl \\
        --out reports/session.md --html reports/session.html --open

Only run this against networks and devices you own or are explicitly
authorized to test.
"""

import argparse
import os
import sys
import threading
import webbrowser

from .logger import SessionLogger, export_csv
from .report import write_html_report, write_report


def _cmd_wifi(args: argparse.Namespace) -> int:
    from .wifi_sniffer import DEFAULT_CHANNELS, run_wifi_sniffer

    channels = [int(c) for c in args.channels.split(",")] if args.channels else DEFAULT_CHANNELS
    with SessionLogger(args.out, "wifi") as logger:
        print(f"[wifi] capturing on {args.iface} -> {logger.path}")
        count = run_wifi_sniffer(args.iface, logger, duration=args.duration,
                                  channels=channels, hop=not args.no_hop)
    print(f"[wifi] logged {count} observations")
    _maybe_report(logger.path, args)
    return 0


def _cmd_ble(args: argparse.Namespace) -> int:
    from .ble_sniffer import run_ble_sniffer

    with SessionLogger(args.out, "ble") as logger:
        print(f"[ble] scanning -> {logger.path}")
        count = run_ble_sniffer(logger, duration=args.duration)
    print(f"[ble] logged {count} observations")
    _maybe_report(logger.path, args)
    return 0


def _cmd_both(args: argparse.Namespace) -> int:
    from .ble_sniffer import run_ble_sniffer
    from .wifi_sniffer import DEFAULT_CHANNELS, run_wifi_sniffer

    channels = [int(c) for c in args.channels.split(",")] if args.channels else DEFAULT_CHANNELS
    with SessionLogger(args.out, "combined") as logger:
        print(f"[both] WiFi on {args.iface} + BLE scan -> {logger.path}")

        wifi_result = {}

        def _run_wifi():
            wifi_result["count"] = run_wifi_sniffer(
                args.iface, logger, duration=args.duration, channels=channels, hop=not args.no_hop
            )

        wifi_thread = threading.Thread(target=_run_wifi, daemon=True)
        wifi_thread.start()

        ble_count = run_ble_sniffer(logger, duration=args.duration)
        wifi_thread.join(timeout=max(args.duration or 0, 5) + 5)

    print(f"[both] logged {wifi_result.get('count', 0)} WiFi + {ble_count} BLE observations")
    _maybe_report(logger.path, args)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    out_path = write_report(args.log, args.out)
    print(f"Report written: {out_path}")
    if args.csv:
        csv_path = export_csv(args.log, args.csv)
        print(f"CSV export:     {csv_path}")
    html_path = None
    if args.html:
        html_path = write_html_report(args.log, args.html)
        print(f"HTML dashboard: {html_path}")
    if args.open:
        _open_dashboard(html_path)
    return 0


def _cmd_live(args: argparse.Namespace) -> int:
    from .live_server import run_live_server

    run_live_server(args.log, args.port, interval=args.interval, open_browser=args.open)
    return 0


def _open_dashboard(html_path) -> None:
    if not html_path:
        print("Error: --open needs --html to know which file to open.", file=sys.stderr)
        return
    webbrowser.open(f"file://{os.path.abspath(html_path)}")


def _maybe_report(log_path: str, args: argparse.Namespace) -> None:
    html_path = None
    if getattr(args, "report", None):
        out_path = write_report(log_path, args.report)
        print(f"Report written: {out_path}")
    if getattr(args, "html", None):
        html_path = write_html_report(log_path, args.html)
        print(f"HTML dashboard: {html_path}")
    if getattr(args, "open", False):
        _open_dashboard(html_path)


def _add_common_capture_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", default="logs", help="Directory for the raw JSONL log (default: logs)")
    parser.add_argument("--duration", type=float, default=None,
                         help="Seconds to capture; omit to run until Ctrl-C")
    parser.add_argument("--report", default=None,
                         help="Optional path to also write a markdown summary report when done")
    parser.add_argument("--html", default=None,
                         help="Optional path to also write an HTML dashboard when done")
    parser.add_argument("--open", action="store_true",
                         help="Open the HTML dashboard in a browser when done (needs --html)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rf_sniffer", description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_wifi = sub.add_parser("wifi", help="Passive WiFi capture (needs a monitor-mode interface)")
    p_wifi.add_argument("--iface", required=True, help="Monitor-mode interface, e.g. wlan1mon")
    p_wifi.add_argument("--channels", help="Comma-separated channel list to hop, e.g. 1,6,11 (default: 1-11)")
    p_wifi.add_argument("--no-hop", action="store_true", help="Stay on the interface's current channel")
    _add_common_capture_args(p_wifi)
    p_wifi.set_defaults(func=_cmd_wifi)

    p_ble = sub.add_parser("ble", help="Passive BLE advertisement scan")
    _add_common_capture_args(p_ble)
    p_ble.set_defaults(func=_cmd_ble)

    p_both = sub.add_parser("both", help="WiFi + BLE capture in parallel, one combined log")
    p_both.add_argument("--iface", required=True, help="Monitor-mode interface, e.g. wlan1mon")
    p_both.add_argument("--channels", help="Comma-separated channel list to hop, e.g. 1,6,11 (default: 1-11)")
    p_both.add_argument("--no-hop", action="store_true", help="Stay on the interface's current channel")
    _add_common_capture_args(p_both)
    p_both.set_defaults(func=_cmd_both)

    p_report = sub.add_parser("report", help="Summarize an existing JSONL log into a markdown report")
    p_report.add_argument("--log", required=True, help="Path to a captured .jsonl session log")
    p_report.add_argument("--out", required=True, help="Path to write the markdown report")
    p_report.add_argument("--csv", default=None, help="Optional path to also export the log as CSV")
    p_report.add_argument("--html", default=None,
                           help="Optional path to also write an HTML dashboard (open it in a browser)")
    p_report.add_argument("--open", action="store_true",
                           help="Open the HTML dashboard in a browser when done (needs --html)")
    p_report.set_defaults(func=_cmd_report)

    p_live = sub.add_parser("live", help="Serve a live-updating dashboard for an in-progress or finished capture")
    p_live.add_argument("--log", required=True, help="Path to the .jsonl session log to watch (can still be growing)")
    p_live.add_argument("--port", type=int, default=8000, help="HTTP port to serve on (default: 8000)")
    p_live.add_argument("--interval", type=float, default=2.0,
                         help="Seconds between dashboard refreshes (default: 2)")
    p_live.add_argument("--open", action="store_true",
                         help="Open the dashboard in a browser once the server starts")
    p_live.set_defaults(func=_cmd_live)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
