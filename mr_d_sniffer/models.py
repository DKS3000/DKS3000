"""Data models for captured RF observations."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WifiObservation:
    """One 802.11 frame of interest (beacon, probe request/response, data)."""

    timestamp: str = field(default_factory=_now_iso)
    frame_type: str = ""  # "beacon" | "probe_req" | "probe_resp" | "data"
    bssid: Optional[str] = None
    client_mac: Optional[str] = None
    ssid: Optional[str] = None
    channel: Optional[int] = None
    rssi: Optional[int] = None
    encryption: Optional[str] = None  # "OPEN" | "WEP" | "WPA" | "WPA2" | "WPA3"
    vendor: Optional[str] = None
    device_name: Optional[str] = None  # from a WPS "Device Name" element, when a client advertises one


@dataclass
class BleObservation:
    """One BLE advertisement."""

    timestamp: str = field(default_factory=_now_iso)
    address: str = ""
    name: Optional[str] = None
    rssi: Optional[int] = None
    tx_power: Optional[int] = None
    manufacturer_ids: list = field(default_factory=list)
    service_uuids: list = field(default_factory=list)
    vendor: Optional[str] = None
