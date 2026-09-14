"""Lightweight active TCP port/service scan for devices already seen with
a known IP address (via Connected Clients IP capture).

This is a deliberate departure from the rest of mr_d_sniffer, which is
purely passive (it only listens, never transmits at a device). Opening a
TCP connection to a device IS a transmission - only run this against
devices you own or are explicitly authorized to test, same as the WiFi/BLE
capture itself. It is opt-in (--scan-ports) and never runs by default.
"""

import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

# A short list of commonly-open ports, not an exhaustive scan - kept small
# so a scan of one device finishes in under a second.
COMMON_PORTS = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
    80: "http", 110: "pop3", 139: "netbios-ssn", 143: "imap", 443: "https",
    445: "smb", 554: "rtsp", 631: "ipp", 993: "imaps", 995: "pop3s",
    1900: "upnp", 3389: "rdp", 5000: "upnp/http-alt", 5353: "mdns",
    7000: "airplay", 8080: "http-alt", 8443: "https-alt", 8888: "http-alt",
    9100: "printer",
}


def _probe_port(ip: str, port: int, timeout: float) -> Optional[int]:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return port
    except OSError:
        return None


def scan_ip(ip: str, ports=None, timeout: float = 0.4, max_workers: int = 12) -> list[dict]:
    """Return open ports on `ip` as [{"port": int, "service": str}, ...]."""
    ports = ports or list(COMMON_PORTS)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(lambda p: _probe_port(ip, p, timeout), ports)
    open_ports = sorted(p for p in results if p is not None)
    return [{"port": p, "service": COMMON_PORTS.get(p, "?")} for p in open_ports]


def scan_many(ips: list[str], timeout: float = 0.4) -> dict[str, dict]:
    """Scan several IPs (sequentially - each is already internally
    concurrent across ports). Returns {ip: {"ports": [...], "scanned_at": iso}}."""
    results = {}
    for ip in ips:
        results[ip] = {
            "ports": scan_ip(ip, timeout=timeout),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }
    return results
