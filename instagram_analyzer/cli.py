"""Command-line entry point.

Usage:
    python -m instagram_analyzer analyze --export path/to/extracted-export --out reports/
    python -m instagram_analyzer fetch --out reports/
"""

import argparse
import json
import sys
from dataclasses import asdict

from .analysis import analyze
from .report import write_report


def _cmd_analyze(args: argparse.Namespace) -> int:
    from .export_parser import parse_export

    profile = parse_export(args.export)
    return _finish(profile, args)


def _cmd_fetch(args: argparse.Namespace) -> int:
    from .graph_api import fetch_profile

    profile = fetch_profile(access_token=args.token, business_account_id=args.account_id)
    return _finish(profile, args)


def _finish(profile, args: argparse.Namespace) -> int:
    result = analyze(profile)
    md_path, html_path = write_report(result, args.out)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(asdict(result), fh, indent=2, default=str)
    print(f"Analyzed {result.total_posts} posts for @{result.username or 'unknown'}")
    print(f"Markdown report: {md_path}")
    print(f"HTML report:     {html_path}")
    if args.json:
        print(f"Raw JSON:        {args.json}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="instagram_analyzer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Analyze an official Instagram data export folder")
    p_analyze.add_argument("--export", required=True, help="Path to the extracted export folder")
    p_analyze.add_argument("--out", default="reports", help="Output directory for the report (default: reports)")
    p_analyze.add_argument("--json", help="Optional path to also dump the raw analysis as JSON")
    p_analyze.set_defaults(func=_cmd_analyze)

    p_fetch = sub.add_parser("fetch", help="Fetch live data via the Instagram Graph API")
    p_fetch.add_argument("--token", help="Access token (defaults to IG_ACCESS_TOKEN env var)")
    p_fetch.add_argument("--account-id", help="IG business account ID (defaults to IG_BUSINESS_ACCOUNT_ID env var)")
    p_fetch.add_argument("--out", default="reports", help="Output directory for the report (default: reports)")
    p_fetch.add_argument("--json", help="Optional path to also dump the raw analysis as JSON")
    p_fetch.set_defaults(func=_cmd_fetch)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
