#!/usr/bin/env python3
"""DGFT Residential Proxy Dashboard.

A small Tkinter app for testing and opening country-specific DGFT browser profiles
using residential proxies and isolated Chrome profiles.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib import error, request
from urllib.parse import quote

import tkinter as tk
from tkinter import messagebox, ttk

DGFT_URL = "https://www.dgft.gov.in"
MULTILOGIN_DIR = Path.home() / "MultiLogin"
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


def find_config_file() -> Path:
    candidates = [
        Path(__file__).resolve().parent / "proxies.json",
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
        raise FileNotFoundError(
            f"No proxies.json file found. Expected one of: {', '.join(str(p) for p in [config_path, *[Path(__file__).resolve().parent / 'proxies.json', Path.home() / 'Applications' / 'DecostaMultiVPN' / 'proxies.json']])}"
        )

    with open(config_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError("proxies.json must contain a JSON object keyed by country name.")
    return data


def get_proxy_url(config: dict) -> str:
    host = config.get("host")
    port = config.get("port")
    username = config.get("username")
    password = config.get("password")
    proxy_type = (config.get("proxy_type") or "http").lower()

    if not host or not port:
        raise ValueError(f"Proxy config is missing host/port: {config}")

    if username and password:
        auth = f"{quote(username)}:{quote(password)}@"
    else:
        auth = ""

    return f"{proxy_type}://{auth}{host}:{port}"


def test_proxy(country: str, config: dict) -> tuple[str, str]:
    proxy_url = get_proxy_url(config)
    proxy_support = {
        "http": proxy_url,
        "https": proxy_url,
    }

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


def find_chrome_executable() -> str | None:
    for candidate in CHROME_PATHS:
        path = shutil.which(candidate)
        if path:
            return path
        if os.path.exists(candidate):
            return candidate
    return None


def build_browser_command(country: str, config: dict, chrome_path: str) -> list[str]:
    profile_dir = MULTILOGIN_DIR / f"dgft_{country}"
    profile_dir.mkdir(parents=True, exist_ok=True)

    proxy_url = get_proxy_url(config)
    cmd = [
        chrome_path,
        "--user-data-dir=" + str(profile_dir),
        "--profile-directory=Default",
        "--new-window",
        f"--proxy-server={proxy_url}",
        f"--lang={LANGUAGES.get(country, 'en-US')}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--disable-blink-features=AutomationControlled",
        DGFT_URL,
    ]
    return cmd


class DashboardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DGFT Residential Proxy Dashboard")
        self.root.geometry("820x520")
        self.root.minsize(700, 420)

        self.config_path = find_config_file()
        self.proxy_data = self._load_data()
        self.country_names = sorted(self.proxy_data.keys())

        self.title_label = ttk.Label(root, text="DGFT Residential Proxy Dashboard", font=("Segoe UI", 18, "bold"))
        self.title_label.pack(pady=(16, 8))

        self.status_var = tk.StringVar(value=f"Loaded proxies from: {self.config_path}")
        self.status_bar = ttk.Label(root, textvariable=self.status_var, foreground="#1b5e20")
        self.status_bar.pack(fill="x", padx=16, pady=(0, 8))

        top = ttk.Frame(root)
        top.pack(fill="x", padx=16, pady=8)

        ttk.Label(top, text="Country:").pack(side="left")
        self.country_var = tk.StringVar(value=self.country_names[0] if self.country_names else "")
        self.country_menu = ttk.Combobox(top, textvariable=self.country_var, values=self.country_names, state="readonly", width=24)
        self.country_menu.pack(side="left", padx=(8, 12))

        self.test_button = ttk.Button(top, text="🔍 Test DGFT", command=self.test_selected)
        self.test_button.pack(side="left", padx=(0, 8))

        self.open_button = ttk.Button(top, text="▶ Open", command=self.open_selected)
        self.open_button.pack(side="left")

        self.test_all_button = ttk.Button(top, text="Test All", command=self.test_all)
        self.test_all_button.pack(side="left", padx=(8, 0))

        columns = ("country", "status", "detail")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=14)
        self.tree.heading("country", text="Country")
        self.tree.heading("status", text="Status")
        self.tree.heading("detail", text="Detail")
        self.tree.column("country", width=120, anchor="center")
        self.tree.column("status", width=120, anchor="center")
        self.tree.column("detail", width=420)
        self.tree.pack(fill="both", expand=True, padx=16, pady=(2, 10))

        self._populate_rows()

    def _load_data(self) -> dict:
        try:
            return load_proxies(self.config_path)
        except FileNotFoundError as exc:
            messagebox.showerror("Missing proxies.json", str(exc))
            return {}

    def _populate_rows(self):
        self.tree.delete(*self.tree.get_children())
        for country in self.country_names:
            status = "pending"
            detail = "Not tested yet"
            self.tree.insert("", "end", values=(country, status, detail))

    def _set_country_status(self, country: str, status: str, detail: str):
        for item in self.tree.get_children():
            if self.tree.item(item, "values")[0] == country:
                self.tree.item(item, values=(country, status, detail))
                break

    def _async_test_country(self, country: str):
        config = self.proxy_data.get(country)
        if not config:
            self._set_country_status(country, "missing", "No config found")
            return

        result, detail = test_proxy(country, config)
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

        chrome_path = find_chrome_executable()
        if not chrome_path:
            messagebox.showerror("Chrome not found", "No Chrome/Chromium executable was found in the standard install paths.")
            return

        cmd = build_browser_command(country, config, chrome_path)
        env = os.environ.copy()
        env["TZ"] = TIMEZONES.get(country, "UTC")
        env["LANG"] = LANGUAGES.get(country, "en-US")
        env["LC_ALL"] = LANGUAGES.get(country, "en_US.UTF-8")

        try:
            subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            self.status_var.set(f"Opened {country.title()} profile in a separate Chrome session.")
        except OSError as exc:
            messagebox.showerror("Launch failed", f"Unable to start Chrome: {exc}")


def main() -> None:
    if not sys.platform.startswith(("linux", "darwin")):
        messagebox.showwarning("Platform warning", "This dashboard is designed for Linux/macOS. Windows support may require additional Chrome path adjustments.")

    root = tk.Tk()
    app = DashboardApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

