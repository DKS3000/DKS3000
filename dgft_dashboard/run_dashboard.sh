# DGFT Residential Proxy Dashboard

A fully automated setup for running isolated DGFT sessions through residential proxies, each with its own Chrome profile and locale/timezone settings.

## What this includes

- Proxy testing against DGFT
- Per-country status tracking
- One-click profile launch for a specific country
- Batch open/test support for all configured countries
- CLI automation for scripts or cron-like usage
- Default configuration generation if no `proxies.json` exists

## Project structure

```text
dgft_dashboard/
├── dgft_dashboard.py
├── proxies.json.example
├── README.md
├── requirements.txt
└── run_dashboard.sh
```

## Quick start

1. Create your local config from the example template:

```bash
cp dgft_dashboard/proxies.json.example dgft_dashboard/proxies.json
```

2. Replace the placeholder values with your real IPRoyal credentials.

3. Run the dashboard:

```bash
python3 dgft_dashboard/dgft_dashboard.py
```

## Automation commands

Create a default config automatically if missing:

```bash
python3 dgft_dashboard/dgft_dashboard.py --setup
```

Test all configured countries and print status:

```bash
python3 dgft_dashboard/dgft_dashboard.py --test-all
```

Open a single country profile:

```bash
python3 dgft_dashboard/dgft_dashboard.py --open canada
```

Open all countries:

```bash
python3 dgft_dashboard/dgft_dashboard.py --open-all
```

Open with a custom Chrome binary:

```bash
python3 dgft_dashboard/dgft_dashboard.py --open india --chrome-path /usr/bin/google-chrome-stable
```

## Shell launcher

You can also run the included launcher:

```bash
bash dgft_dashboard/run_dashboard.sh
```

This wrapper starts the dashboard and passes through optional arguments.

## Features

- Keeps a separate browser profile per country under `~/MultiLogin/dgft_<country>`
- Uses the correct timezone and language per country
- Allows stronger automation for repeated DGFT sessions
- Handles missing config files gracefully
- Keeps cookies and sessions isolated for each country profile

## Notes

- Chrome must be installed in a standard path or provided through `--chrome-path`.
- The dashboard prefers `dgft_dashboard/proxies.json` and will also look for older config paths if needed.
- If a proxy is blocked with `403`, it usually indicates the residential IP is flagged and should be rotated by your provider.
