# DGFT Residential Proxy Dashboard

This project adds a simple desktop dashboard for testing and launching DGFT sessions through isolated Chrome profiles using residential proxies.

## Structure

```text
DGFT Dashboard/
├── dgft_dashboard.py
├── proxies.json.example
├── README.md
└── requirements.txt
```

## Requirements

- Python 3.10+
- Google Chrome or Chromium installed
- Tkinter support (`python3-tk` on Linux)
- Access to residential proxy credentials for the countries you plan to use

## Setup

1. Copy the example config:

```bash
cp dgft_dashboard/proxies.json.example dgft_dashboard/proxies.json
```

2. Replace the placeholder credentials in `proxies.json` with your real IPRoyal values.

3. Install the Python dependency:

```bash
python3 -m pip install -r dgft_dashboard/requirements.txt
```

4. Run the dashboard:

```bash
python3 dgft_dashboard/dgft_dashboard.py
```

## Features

- Tests each configured country against the DGFT endpoint.
- Shows status whether the proxy is working, blocked, or failing.
- Opens a separate Chrome profile per country with the correct locale and timezone.
- Keeps cookies and sessions isolated under `~/MultiLogin/dgft_<country>`.

## Notes

- If Chrome cannot be found, update `CHROME_PATHS` in `dgft_dashboard.py`.
- The script will look for `proxies.json` in the app folder first, then the older `~/Applications/DecostaMultiVPN/` path.
- For more than four countries, add additional entries to the JSON file using the same key/value format.
