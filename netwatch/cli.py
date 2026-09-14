"""Command-line entry point for the netwatch monitoring console.

Usage:
    python -m netwatch serve --hosts hosts.txt --rf-log-dir logs/ --port 8080
    python -m netwatch serve --host 10.0.0.1:router --host 10.0.0.2 --rf-log logs/combined_...jsonl
"""

import argparse
import sys
from typing import List

from rf_sniffer.logger import SessionLogger

from .ip_monitor import IpMonitor
from .models import IpTarget
from .store import CachedJsonlSource
from .web import create_app


def parse_hosts_file(path: str) -> List[IpTarget]:
    """One target per line: `ip` or `ip,hostname`. Blank lines and lines
    starting with `#` are ignored."""
    targets = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",", 1)]
            hostname = parts[1] if len(parts) > 1 and parts[1] else None
            targets.append(IpTarget(ip=parts[0], hostname=hostname))
    return targets


def parse_host_args(entries: List[str]) -> List[IpTarget]:
    targets = []
    for entry in entries:
        ip, _, hostname = entry.partition(":")
        targets.append(IpTarget(ip=ip.strip(), hostname=(hostname.strip() or None)))
    return targets


def _cmd_serve(args: argparse.Namespace) -> int:
    targets: List[IpTarget] = []
    if args.hosts:
        targets.extend(parse_hosts_file(args.hosts))
    targets.extend(parse_host_args(args.host_entry))
    if not targets:
        print("Error: no IP targets given (use --hosts FILE or --host IP[:NAME])", file=sys.stderr)
        return 1

    ip_logger = SessionLogger(args.ip_log_dir, "ip_events")
    monitor = IpMonitor(targets, interval=args.interval, timeout=args.timeout, on_event=ip_logger.write)
    monitor.poll_once()  # establish initial up/down state before the console opens
    monitor.start()

    ip_event_source = CachedJsonlSource(glob_dir=args.ip_log_dir, glob_pattern="ip_events_*.jsonl")
    rf_source = CachedJsonlSource(paths=args.rf_log, glob_dir=args.rf_log_dir)

    app = create_app(monitor, ip_event_source, rf_source)
    print(f"[netwatch] monitoring {len(targets)} host(s) every {args.interval}s -> {ip_logger.path}")
    print(f"[netwatch] console: http://{args.bind}:{args.port}/")
    try:
        app.run(host=args.bind, port=args.port, debug=False, use_reloader=False)
    finally:
        monitor.stop()
        ip_logger.close()
    return 0


def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--hosts", help="Path to a hosts file (one 'ip' or 'ip,hostname' per line)")
    parser.add_argument("--host", dest="host_entry", action="append", default=[],
                         help="Add one target as 'ip' or 'ip:hostname' (repeatable)")
    parser.add_argument("--interval", type=float, default=30.0,
                         help="Ping poll interval in seconds (default: 30)")
    parser.add_argument("--timeout", type=float, default=1.0,
                         help="Ping timeout in seconds (default: 1)")
    parser.add_argument("--ip-log-dir", default="logs",
                         help="Directory for IP wake/sleep JSONL logs (default: logs)")
    parser.add_argument("--rf-log", action="append", default=[],
                         help="Path to an rf_sniffer JSONL log to include (repeatable)")
    parser.add_argument("--rf-log-dir", default=None,
                         help="Directory to glob for rf_sniffer '*.jsonl' logs (e.g. logs/)")
    parser.add_argument("--bind", default="127.0.0.1", help="Address to bind the console to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port for the console (default: 8080)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netwatch", description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="Start the IP + RF monitoring web console")
    _add_serve_args(p_serve)
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
