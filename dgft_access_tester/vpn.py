"""VPN control via user-configured commands (provider CLI of your choice).

Config example (vpn_config.json):
{
  "provider": "ExampleVPN",
  "status_cmd": ["examplevpn", "status"],
  "disconnect_cmd": ["examplevpn", "disconnect"],
  "servers": {"Germany": {"server": "de1", "connect_cmd": ["examplevpn", "connect", "de1"]}}
}
status_cmd must exit 0 only while the VPN tunnel is up.
"""
import json
import re
import subprocess
import urllib.request

IP_URL = "https://api.ipify.org"
_IP_RE = re.compile(r"^[0-9a-fA-F.:]{3,45}$")


def public_ip(timeout=10):
    with urllib.request.urlopen(IP_URL, timeout=timeout) as r:
        ip = r.read().decode().strip()
    if not _IP_RE.match(ip):
        raise RuntimeError("unexpected public IP response")
    return ip


def _run(cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, timeout=timeout, shell=False).returncode == 0


class VPN:
    def __init__(self, config, baseline_ip=None, ip_func=public_ip):
        self.cfg = config
        self.ip_func = ip_func
        self.baseline_ip = baseline_ip
        self.country = None
        self.server = None

    @classmethod
    def from_file(cls, path):
        with open(path) as f:
            return cls(json.load(f))

    @property
    def provider(self):
        return self.cfg.get("provider", "unknown")

    def countries(self):
        return sorted(self.cfg.get("servers", {}))

    def connect(self, country):
        entry = self.cfg.get("servers", {}).get(country)
        if not entry:
            raise ValueError("unknown country: %s" % country)
        if self.baseline_ip is None:
            self.baseline_ip = self.ip_func()
        if not _run(entry["connect_cmd"]):
            raise RuntimeError("VPN connect command failed")
        self.country, self.server = country, entry.get("server", "")
        return self.verify()

    def disconnect(self):
        if self.cfg.get("disconnect_cmd"):
            _run(self.cfg["disconnect_cmd"])
        self.country = self.server = None

    def verify(self):
        """Return state dict; connected only if tunnel is up AND public IP changed."""
        state = {"connected": False, "provider": self.provider, "country": self.country,
                 "server": self.server, "public_ip": None}
        try:
            if not _run(self.cfg["status_cmd"], timeout=20):
                return state
            ip = self.ip_func()
        except Exception:
            return state
        state["public_ip"] = ip
        state["connected"] = bool(self.country) and ip != self.baseline_ip
        return state
