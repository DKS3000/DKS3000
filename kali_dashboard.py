#!/usr/bin/env python3
"""
Kali Dashboard - All-in-One Network Monitoring & Automation Tool
================================================================

A comprehensive security/monitoring dashboard for Kali Linux offering:
- Public IP monitoring (via ipify)
- Live and offline packet capture (PyShark/Wireshark)
- UI automation testing (Selenium)
- SSH router log retrieval (Paramiko)
- SQLite logging & persistence

Author:  decosta sniffer system ip logger
GitHub: https://github.com/yourusername/kali-dashboard
License: MIT

Installation (one-time setup on Kali):
    sudo apt update && sudo apt install -y python3-pip tshark chromium-driver
    pip3 install pyshark requests selenium paramiko

Usage:
    python3 kali_dashboard.py                # Interactive menu
    python3 kali_dashboard.py --quick        # Run all tools once
    python3 kali_dashboard.py --menu         # Force menu mode

GitHub Repository Structure:
    kali-dashboard/
    ├── kali_dashboard.py       # This single-file tool
    ├── requirements.txt        # Python dependencies
    ├── LICENSE                 # MIT license
    ├── README.md               # Documentation
    └── docs/                   # Screenshots, examples
"""

import argparse
import datetime
import getpass
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

# Optional imports - check availability at runtime
try:
    import pyshark
    PYSHARK_AVAILABLE = True
except ImportError:
    PYSHARK_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import paramiko
    SSH_AVAILABLE = True
except ImportError:
    SSH_AVAILABLE = False


# ============================================================
# CONFIGURATION - Edit these defaults for your environment
# ============================================================
VERSION = "2.0.0"
REPO_URL = "https://github.com/yourusername/kali-dashboard"

DB_DIR = Path.home() / "kali_dashboard"
DB_PATH = DB_DIR / "monitor.db"

IPIFY_URL = "https://api.ipify.org"
IP_MONITOR_INTERVAL = 10  # seconds

DEFAULT_INTERFACE = "eth0"      # Change to your active interface
DEFAULT_BPF_FILTER = "tcp port 443"  # Common HTTPS traffic filter

TEST_URL_FOR_UI = "https://example.com"  # Safe demo page

SSH_DEFAULTS = {
    "host": "192.168.1.1",      # Replace with your router IP
    "username": "admin",
    "password": "",             # Will prompt if empty
    "command": "show log"       # Typical router log command
}


# ============================================================
# DATABASE & LOGGING HELPERS
# ============================================================
def ensure_db():
    """Create database and tables if they don't exist."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS ip_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        source_ip TEXT,
        action TEXT,
        activity TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ip_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        old_ip TEXT,
        new_ip TEXT,
        reason TEXT
    )""")
    conn.commit()
    conn.close()


def log_event(source_ip, action, activity):
    """Write a log entry to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        ts = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT INTO ip_logs (timestamp, source_ip, action, activity) VALUES (?,?,?,?)",
            (ts, source_ip, action, activity)
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}")


def log_ip_change(old_ip, new_ip, reason="public IP change"):
    """Record an IP address change."""
    try:
        conn = sqlite3.connect(DB_PATH)
        ts = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT INTO ip_changes (timestamp, old_ip, new_ip, reason) VALUES (?,?,?,?)",
            (ts, old_ip, new_ip, reason)
        )
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Database error: {e}")


def view_recent(limit=15):
    """Retrieve recent logs and IP changes from database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    print(f"\n--- Last {limit} events ---")
    c.execute(
        "SELECT timestamp, source_ip, action, activity FROM ip_logs "
        "ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = c.fetchall()
    if not rows:
        print("  (no events logged yet)")
    for ts, source_ip, action, activity in rows:
        print(f"  [{ts}] {source_ip or '-'} :: {action} - {activity}")

    print(f"\n--- Last {limit} IP changes ---")
    c.execute(
        "SELECT timestamp, old_ip, new_ip, reason FROM ip_changes "
        "ORDER BY id DESC LIMIT ?", (limit,)
    )
    rows = c.fetchall()
    if not rows:
        print("  (no IP changes recorded yet)")
    for ts, old_ip, new_ip, reason in rows:
        print(f"  [{ts}] {old_ip or '?'} -> {new_ip} ({reason})")

    conn.close()


# ============================================================
# PUBLIC IP MONITOR (requests + ipify)
# ============================================================
def get_public_ip(timeout=5):
    """Fetch the current public IP address from ipify."""
    if not REQUESTS_AVAILABLE:
        print("[!] 'requests' is not installed - run: pip3 install requests")
        return None
    try:
        resp = requests.get(IPIFY_URL, timeout=timeout)
        resp.raise_for_status()
        return resp.text.strip()
    except requests.RequestException as e:
        print(f"[!] Failed to fetch public IP: {e}")
        return None


def monitor_public_ip(iterations=1, interval=IP_MONITOR_INTERVAL):
    """
    Poll the public IP address, logging every check and any change.

    iterations: number of checks to perform (use a large number or a
                KeyboardInterrupt to run indefinitely from the menu).
    """
    print(f"\n[*] Monitoring public IP every {interval}s "
          f"({iterations if iterations > 0 else 'until interrupted'} checks)...")
    last_ip = None
    count = 0
    try:
        while iterations <= 0 or count < iterations:
            ip = get_public_ip()
            if ip:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Public IP: {ip}")
                log_event(ip, "ip_check", "public IP polled")
                if last_ip and ip != last_ip:
                    print(f"[!] IP CHANGED: {last_ip} -> {ip}")
                    log_ip_change(last_ip, ip)
                last_ip = ip
            count += 1
            if iterations <= 0 or count < iterations:
                time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[*] IP monitoring stopped by user.")


# ============================================================
# PACKET CAPTURE (PyShark / Wireshark)
# ============================================================
def capture_packets_live(interface=DEFAULT_INTERFACE, bpf_filter=DEFAULT_BPF_FILTER,
                          packet_count=20):
    """Capture packets live from a network interface using PyShark."""
    if not PYSHARK_AVAILABLE:
        print("[!] 'pyshark' is not installed - run: pip3 install pyshark "
              "(and ensure tshark is installed via apt)")
        return

    print(f"\n[*] Capturing {packet_count} packets on '{interface}' "
          f"(filter: '{bpf_filter}')...")
    try:
        capture = pyshark.LiveCapture(interface=interface, bpf_filter=bpf_filter)
        seen = 0
        for packet in capture.sniff_continuously(packet_count=packet_count):
            seen += 1
            src = getattr(getattr(packet, "ip", None), "src", "?")
            dst = getattr(getattr(packet, "ip", None), "dst", "?")
            proto = packet.highest_layer
            print(f"  #{seen} {proto} {src} -> {dst}")
            log_event(src, "packet_capture", f"{proto} -> {dst}")
        capture.close()
        print(f"[*] Capture complete: {seen} packets captured.")
    except Exception as e:
        print(f"[!] Packet capture failed: {e}")
        print("    (Live capture usually requires root privileges - try sudo)")


def capture_packets_offline(pcap_path):
    """Read and summarize packets from an existing .pcap/.pcapng file."""
    if not PYSHARK_AVAILABLE:
        print("[!] 'pyshark' is not installed - run: pip3 install pyshark")
        return

    if not os.path.isfile(pcap_path):
        print(f"[!] File not found: {pcap_path}")
        return

    print(f"\n[*] Reading capture file: {pcap_path}")
    try:
        capture = pyshark.FileCapture(pcap_path)
        seen = 0
        for packet in capture:
            seen += 1
            src = getattr(getattr(packet, "ip", None), "src", "?")
            dst = getattr(getattr(packet, "ip", None), "dst", "?")
            proto = packet.highest_layer
            print(f"  #{seen} {proto} {src} -> {dst}")
            log_event(src, "packet_capture_offline", f"{proto} -> {dst} ({pcap_path})")
        capture.close()
        print(f"[*] Finished reading {seen} packets from file.")
    except Exception as e:
        print(f"[!] Failed to read capture file: {e}")


# ============================================================
# UI AUTOMATION TESTING (Selenium)
# ============================================================
def run_ui_test(url=TEST_URL_FOR_UI, headless=True):
    """Open a page in a headless Chromium browser and report basic results."""
    if not SELENIUM_AVAILABLE:
        print("[!] 'selenium' is not installed - run: pip3 install selenium "
              "(and ensure chromium-driver is installed via apt)")
        return

    print(f"\n[*] Running UI automation test against: {url}")
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        start = time.time()
        driver.get(url)
        elapsed = time.time() - start
        title = driver.title
        print(f"[*] Page loaded in {elapsed:.2f}s - title: '{title}'")
        log_event(None, "ui_test", f"loaded {url} in {elapsed:.2f}s, title='{title}'")
    except Exception as e:
        print(f"[!] UI automation test failed: {e}")
        log_event(None, "ui_test_error", str(e))
    finally:
        if driver is not None:
            driver.quit()


# ============================================================
# SSH ROUTER LOG RETRIEVAL (Paramiko)
# ============================================================
def fetch_ssh_logs(host=None, username=None, password=None, command=None):
    """Connect to a router/device over SSH and retrieve log output."""
    if not SSH_AVAILABLE:
        print("[!] 'paramiko' is not installed - run: pip3 install paramiko")
        return

    host = host or SSH_DEFAULTS["host"]
    username = username or SSH_DEFAULTS["username"]
    command = command or SSH_DEFAULTS["command"]
    password = password or SSH_DEFAULTS["password"]
    if not password:
        password = getpass.getpass(f"SSH password for {username}@{host}: ")

    print(f"\n[*] Connecting to {username}@{host} via SSH...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.load_system_host_keys()
        client.connect(host, username=username, password=password, timeout=10)
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode(errors="replace")
        errors = stderr.read().decode(errors="replace")
        if output:
            print("--- Output ---")
            print(output)
        if errors:
            print("--- Errors ---")
            print(errors)
        log_event(host, "ssh_log_fetch", f"ran '{command}' on {host}")
    except paramiko.SSHException as e:
        print(f"[!] SSH connection failed: {e}")
        print("    If this is a first-time connection, add the host key with "
              "`ssh-keyscan -H <host> >> ~/.ssh/known_hosts` first.")
    except Exception as e:
        print(f"[!] Unexpected error retrieving SSH logs: {e}")
    finally:
        client.close()


# ============================================================
# INTERACTIVE MENU
# ============================================================
def print_banner():
    print("=" * 60)
    print(f"  Kali Dashboard v{VERSION}")
    print("  Network Monitoring & Automation Tool")
    print("=" * 60)
    print(f"  pyshark:   {'available' if PYSHARK_AVAILABLE else 'NOT installed'}")
    print(f"  requests:  {'available' if REQUESTS_AVAILABLE else 'NOT installed'}")
    print(f"  selenium:  {'available' if SELENIUM_AVAILABLE else 'NOT installed'}")
    print(f"  paramiko:  {'available' if SSH_AVAILABLE else 'NOT installed'}")
    print(f"  database:  {DB_PATH}")
    print("=" * 60)


def print_menu():
    print("""
  1) Check public IP once
  2) Monitor public IP continuously (Ctrl-C to stop)
  3) Live packet capture
  4) Read packets from a .pcap file
  5) Run UI automation test (Selenium)
  6) Fetch router logs over SSH
  7) View recent database logs
  0) Exit
""")


def interactive_menu():
    print_banner()
    while True:
        print_menu()
        choice = input("Select an option: ").strip()

        if choice == "1":
            ip = get_public_ip()
            if ip:
                print(f"Public IP: {ip}")
                log_event(ip, "ip_check", "manual check")
        elif choice == "2":
            monitor_public_ip(iterations=0)
        elif choice == "3":
            iface = input(f"Interface [{DEFAULT_INTERFACE}]: ").strip() or DEFAULT_INTERFACE
            bpf = input(f"BPF filter [{DEFAULT_BPF_FILTER}]: ").strip() or DEFAULT_BPF_FILTER
            count = input("Packet count [20]: ").strip()
            count = int(count) if count.isdigit() else 20
            capture_packets_live(iface, bpf, count)
        elif choice == "4":
            path = input("Path to .pcap/.pcapng file: ").strip()
            capture_packets_offline(path)
        elif choice == "5":
            url = input(f"URL [{TEST_URL_FOR_UI}]: ").strip() or TEST_URL_FOR_UI
            run_ui_test(url)
        elif choice == "6":
            host = input(f"Router host [{SSH_DEFAULTS['host']}]: ").strip() or SSH_DEFAULTS["host"]
            username = input(f"Username [{SSH_DEFAULTS['username']}]: ").strip() or SSH_DEFAULTS["username"]
            command = input(f"Command [{SSH_DEFAULTS['command']}]: ").strip() or SSH_DEFAULTS["command"]
            fetch_ssh_logs(host=host, username=username, command=command)
        elif choice == "7":
            view_recent()
        elif choice == "0":
            print("Goodbye.")
            break
        else:
            print("Invalid selection, try again.")


# ============================================================
# QUICK MODE - run everything once, non-interactively
# ============================================================
def run_quick_all():
    print_banner()
    print("\n[*] Quick mode: running all tools once with defaults.\n")

    ip = get_public_ip()
    if ip:
        print(f"Public IP: {ip}")
        log_event(ip, "ip_check", "quick mode check")

    if PYSHARK_AVAILABLE:
        capture_packets_live(packet_count=10)
    else:
        print("[-] Skipping packet capture (pyshark not installed).")

    if SELENIUM_AVAILABLE:
        run_ui_test()
    else:
        print("[-] Skipping UI automation test (selenium not installed).")

    if SSH_AVAILABLE and SSH_DEFAULTS["host"]:
        print("[-] Skipping SSH log fetch in quick mode (requires credentials); "
              "use the interactive menu or --ssh-host/--ssh-user/--ssh-command.")

    view_recent()


# ============================================================
# ENTRY POINT
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="Kali Dashboard - All-in-One Network Monitoring & Automation Tool"
    )
    parser.add_argument("--quick", action="store_true",
                         help="Run all available tools once with default settings and exit.")
    parser.add_argument("--menu", action="store_true",
                         help="Force the interactive menu (default when no flags are given).")
    parser.add_argument("--ssh-host", help="Router/device host for SSH log retrieval.")
    parser.add_argument("--ssh-user", help="SSH username for log retrieval.")
    parser.add_argument("--ssh-command", help="Command to run over SSH for log retrieval.")
    args = parser.parse_args()

    ensure_db()

    if args.ssh_host or args.ssh_user or args.ssh_command:
        fetch_ssh_logs(host=args.ssh_host, username=args.ssh_user, command=args.ssh_command)
        return

    if args.quick:
        run_quick_all()
    else:
        interactive_menu()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] Interrupted, exiting.")
        sys.exit(0)
