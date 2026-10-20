#!/usr/bin/env python3
"""DGFT Residential Proxy Dashboard.

A self-contained automation-friendly dashboard for testing and opening country-specific
DGFT sessions through residential proxy + isolated Chrome profile combinations.

Usage examples:
  python3 dgft_dashboard.py --setup
  python3 dgft_dashboard.py --test-all
  python3 dgft_dashboard.py --open canada
  python3 dgft_dashboard.py --open-all
  python3 dgft_dashboard.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib import error, request
from urllib.parse import quote

import tkinter as tk
from tkinter import messagebox, ttk

DGFT_URL = "https://www.dgft.gov.in"
MULTILOGIN_DIR = Path.home() / "MultiLogin"
DEFAULT_COUNTRIES = ["canada", "uruguay", "liberia", "india"]
TIMEZONES = {
    "canada": "America/Toronto",
    "uruguay": "America/Montevideo",
    "liberia": "Africa/Monrovia",
    "india": "Asia/Kolkata",
}
LANGUAGES = {
    "canada": "en-CA",
    "uruguay": "es-UY",
    "liberia": "en-LR",
    "india": "en-IN",
}
CHROME_PATHS = [
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    os.path.expanduser("~/Applications/Chromium.app/Contents/MacOS/Chromium"),
]
CONFIG_TEMPLATE = {
    "canada": {
        "host": "geo.iproyal.com",
        "port": 12321,
        "username": "YOUR_IPROYAL_USERNAME_country-ca",
        "password": "YOUR_IPROYAL_PASSWORD",
        "proxy_type": "http",
        "country_code": "CA",
        "reader_id": "CANADA",
    },
    "uruguay": {
        "host": "geo.iproyal.com",
        "port": 12321,
        "username": "YOUR_IPROYAL_USERNAME_country-uy",
        "password": "YOUR_IPROYAL_PASSWORD",
        "proxy_type": "http",
        "country_code": "UY",
        "reader_id": "URUGUAY",
    },
    "liberia": {
        "host": "geo.iproyal.com",
        "port": 12321,
        "username": "YOUR_IPROYAL_USERNAME_country-lr",
        "password": "YOUR_IPROYAL_PASSWORD",
        "proxy_type": "http",
        "country_code": "LR",
        "reader_id": "LIBERIA",
    },
    "india": {
        "host": "geo.iproyal.com",
        "port": 12321,
        "username": "YOUR_IPROYAL_USERNAME_country-in",
        "password": "YOUR_IPROYAL_PASSWORD",
        "proxy_type": "http",
        "country_code": "IN",
        "reader_id": "INDIA",
    },
}


def app_dir() -> Path:
    return Path(__file__).resolve().parent


def get_default_config_path() -> Path:
    return app_dir() / "proxies.json"


def ensure_config_file(force: bool = False) -> Path:
    config_path = get_default_config_path()
    if force or not config_path.exists():
        config_path.write_text(json.dumps(CONFIG_TEMPLATE, indent=2) + "\n", encoding="utf-8")
    return config_path


def find_config_file() -> Path:
    candidates = [
        app_dir() / "proxies.json",
        Path.home() / "Applications" / "DecostaMultiVPN" / "proxies.json",
        Path.home() / "dgft" / "proxies.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def load_proxies(path: Path | None = None) -> dict:
    config_path = path or find_config_file()
    if not config_path.exists():
        ensure_config_file()
        config_path = get_default_config_path()

    with open(config_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("proxies.json must contain a JSON object keyed by country key names.")
    return data


def get_proxy_url(config: dict) -> str:
    host = config.get("host")
    port = config.get("port")
    username = config.get("username")
    password = config.get("password")
    proxy_type = (config.get("proxy_type") or "http").lower()

    if not host or not port:
        raise ValueError(f"Proxy config is missing host/port: {config}")

    auth = ""
    if username and password:
        auth = f"{quote(username)}:{quote(password)}@"

    return f"{proxy_type}://{auth}{host}:{port}"


def test_proxy(config: dict) -> tuple[str, str]:
    proxy_url = get_proxy_url(config)
    proxy_support = {"http": proxy_url, "https": proxy_url}
    opener = request.build_opener(request.ProxyHandler(proxy_support))
    req = request.Request(
        DGFT_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DGFT Dashboard Test/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    try:
        with opener.open(req, timeout=20) as response:
            status_code = getattr(response, "status", 200)
            if 200 <= status_code < 400:
                return "ok", f"HTTP {status_code} OK"
            return "warn", f"HTTP {status_code}"
    except error.HTTPError as exc:
        if exc.code == 403:
            return "blocked", "403 Forbidden - residential IP may be flagged"
        return "error", f"HTTP {exc.code}: {exc.reason}"
    except error.URLError as exc:
        return "error", f"URL error: {exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return "error", f"Unexpected error: {exc}"


def find_chrome_executable(custom_path: str | None = None) -> str | None:
    if custom_path:
        if os.path.exists(custom_path):
            return custom_path
        if shutil.which(custom_path):
            return shutil.which(custom_path)

    for candidate in CHROME_PATHS:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        if os.path.exists(candidate):
            return candidate
    return None


def build_browser_command(country: str, config: dict, chrome_path: str, incognito: bool = False) -> list[str]:
    profile_dir = MULTILOGIN_DIR / f"dgft_{country}"
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        chrome_path,
        "--user-data-dir=" + str(profile_dir),
        "--profile-directory=Default",
        "--new-window",
        f"--proxy-server={get_proxy_url(config)}",
        f"--lang={LANGUAGES.get(country, 'en-US')}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--disable-blink-features=AutomationControlled",
    ]
    if incognito:
        cmd.append("--incognito")
    cmd.append(DGFT_URL)
    return cmd


def open_country(country: str, config: dict, chrome_path: str | None = None, incognito: bool = False) -> dict:
    chrome_path = chrome_path or find_chrome_executable()
    if not chrome_path:
        return {"ok": False, "message": "No Chrome/Chromium executable found in standard install paths."}

    cmd = build_browser_command(country, config, chrome_path, incognito=incognito)
    env = os.environ.copy()
    env["TZ"] = TIMEZONES.get(country, "UTC")
    env["LANG"] = LANGUAGES.get(country, "en-US")
    env["LC_ALL"] = f"{LANGUAGES.get(country, 'en_US')}.UTF-8".replace("-", "_")

    try:
        subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"ok": True, "message": f"Opened profile for {country.title()}"}
    except OSError as exc:
        return {"ok": False, "message": f"Unable to start Chrome: {exc}"}


class DashboardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DGFT Residential Proxy Dashboard")
        self.root.geometry("940x560")
        self.root.minsize(760, 420)

        self.config_path = find_config_file()
        self.proxy_data = self._load_data()
        self.country_names = sorted(self.proxy_data.keys())

        self.title_label = ttk.Label(root, text="DGFT Residential Proxy Dashboard", font=("Segoe UI", 18, "bold"))
        self.title_label.pack(pady=(16, 8))

        self.status_var = tk.StringVar(value=f"Loaded proxies from: {self.config_path}")
        self.status_bar = ttk.Label(root, textvariable=self.status_var, foreground="#1b5e20")
        self.status_bar.pack(fill="x", padx=16, pady=(0, 8))

        self.top = ttk.Frame(root)
        self.top.pack(fill="x", padx=16, pady=8)

        ttk.Label(self.top, text="Country:").pack(side="left")
        self.country_var = tk.StringVar(value=self.country_names[0] if self.country_names else "")
        self.country_menu = ttk.Combobox(self.top, textvariable=self.country_var, values=self.country_names, state="readonly", width=24)
        self.country_menu.pack(side="left", padx=(8, 12))

        self.test_button = ttk.Button(self.top, text="🔍 Test DGFT", command=self.test_selected)
        self.test_button.pack(side="left", padx=(0, 8))

        self.open_button = ttk.Button(self.top, text="▶ Open", command=self.open_selected)
        self.open_button.pack(side="left")

        self.open_all_button = ttk.Button(self.top, text="Open All", command=self.open_all)
        self.open_all_button.pack(side="left", padx=(8, 0))

        self.test_all_button = ttk.Button(self.top, text="Test All", command=self.test_all)
        self.test_all_button.pack(side="left", padx=(8, 0))

        self.setup_button = ttk.Button(self.top, text="Setup Config", command=self.setup_config)
        self.setup_button.pack(side="left", padx=(8, 0))

        columns = ("country", "status", "detail")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=14)
        self.tree.heading("country", text="Country")
        self.tree.heading("status", text="Status")
        self.tree.heading("detail", text="Detail")
        self.tree.column("country", width=120, anchor="center")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("detail", width=520)
        self.tree.pack(fill="both", expand=True, padx=16, pady=(2, 10))

        self._populate_rows()

    def _load_data(self) -> dict:
        try:
            return load_proxies(find_config_file())
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as exc:
            messagebox.showerror("Invalid proxies.json", f"Could not parse config: {exc}")
            return {}

    def _populate_rows(self):
        self.tree.delete(*self.tree.get_children())
        for country in self.country_names:
            self.tree.insert("", "end", values=(country, "pending", "Not tested yet"))

    def _set_country_status(self, country: str, status: str, detail: str):
        for item in self.tree.get_children():
            if self.tree.item(item, "values")[0] == country:
                self.tree.item(item, values=(country, status, detail))
                return

    def _async_test_country(self, country: str):
        config = self.proxy_data.get(country)
        if not config:
            self._set_country_status(country, "missing", "No config found")
            return

        result, detail = test_proxy(config)
        label = {"ok": "✅ OK", "blocked": "❌ Blocked", "warn": "⚠ Warning", "error": "❌ Error"}.get(result, result)
        self._set_country_status(country, label, detail)

        if result == "ok":
            self.status_var.set(f"{country.title()} proxy is working.")
        else:
            self.status_var.set(f"{country.title()} proxy check failed: {detail}")

    def test_selected(self):
        country = self.country_var.get()
        if not country:
            messagebox.showwarning("No country selected", "Choose a country from the dropdown.")
            return
        thread = threading.Thread(target=self._async_test_country, args=(country,), daemon=True)
        thread.start()

    def test_all(self):
        if not self.country_names:
            messagebox.showwarning("No proxies", "No proxy entries were found. Run Setup Config to generate a default config.")
            return

        for country in self.country_names:
            self._set_country_status(country, "testing", "Running DGFT check...")
            thread = threading.Thread(target=self._async_test_country, args=(country,), daemon=True)
            thread.start()

    def open_selected(self):
        country = self.country_var.get()
        if not country:
            messagebox.showwarning("No country selected", "Choose a country first.")
            return

        config = self.proxy_data.get(country)
        if not config:
            messagebox.showerror("Missing config", f"No proxy config found for {country}.")
            return

        result = open_country(country, config)
        if result["ok"]:
            self.status_var.set(result["message"])
        else:
            messagebox.showerror("Launch failed", result["message"])

    def open_all(self):
        if not self.country_names:
            messagebox.showwarning("No proxies", "No proxy entries were found.")
            return

        for country in self.country_names:
            config = self.proxy_data.get(country)
            if not config:
                continue
            result = open_country(country, config)
            if not result["ok"]:
                self.status_var.set(f"{country.title()} launch failed: {result['message']}")
                break
            self.status_var.set(f"Opened all countries: {', '.join(self.country_names)}")

    def setup_config(self):
        config_path = ensure_config_file(force=True)
        self.config_path = config_path
        self.proxy_data = load_proxies(config_path)
        self.country_names = sorted(self.proxy_data.keys())
        self.country_var.set(self.country_names[0] if self.country_names else "")
        self.country_menu.configure(values=self.country_names)
        self._populate_rows()
        self.status_var.set(f"Default config created at: {config_path}")


def print_status_table(data: dict) -> None:
    print("DGFT proxy status")
    print("=" * 72)
    for key in sorted(data):
        config = data[key]
        result, detail = test_proxy(config)
        label = {"ok": "OK", "blocked": "BLOCKED", "warn": "WARN", "error": "ERROR"}.get(result, result.upper())
        print(f"{key:<10} {label:<8} {detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="DGFT Residential Proxy Dashboard")
    parser.add_argument("--setup", action="store_true", help="Create a default proxies.json file if missing")
    parser.add_argument("--test-all", action="store_true", help="Run DGFT tests for all configured countries and print results")
    parser.add_argument("--open", metavar="COUNTRY", help="Open a specific country profile in Chrome")
    parser.add_argument("--open-all", action="store_true", help="Open all configured country sessions")
    parser.add_argument("--chrome-path", help="Explicit Chrome/Chromium executable path")
    parser.add_argument("--incognito", action="store_true", help="Open Chrome in incognito mode")
    args = parser.parse_args()

    if args.setup:
        ensure_config_file(force=True)
        print(f"Created default configuration at: {get_default_config_path()}")
        return

    if args.test_all:
        proxies = load_proxies(find_config_file())
        print_status_table(proxies)
        return

    if args.open:
        proxies = load_proxies(find_config_file())
        country = args.open.lower()
        if country not in proxies:
            print(f"Unknown country '{country}'. Available: {', '.join(sorted(proxies))}")
            return
        result = open_country(country, proxies[country], chrome_path=args.chrome_path, incognito=args.incognito)
        print(result["message"])
        return

    if args.open_all:
        proxies = load_proxies(find_config_file())
        for country in sorted(proxies):
            result = open_country(country, proxies[country], chrome_path=args.chrome_path, incognito=args.incognito)
            print(result["message"])
        return

    if not sys.platform.startswith(("linux", "darwin")):
        print("This dashboard is designed for Linux/macOS. Windows may require manual Chrome path adjustments.")

    root = tk.Tk()
    _ = DashboardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
