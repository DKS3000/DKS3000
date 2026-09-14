"""Passive 802.11 (WiFi) capture via a monitor-mode interface.

Requires:
  - A wireless adapter that supports monitor mode.
  - The interface already switched to monitor mode, e.g.:
        sudo ip link set wlan1 down
        sudo iw dev wlan1 set type monitor
        sudo ip link set wlan1 up
    (or `sudo airmon-ng start wlan1`)
  - Root privileges (raw 802.11 capture needs CAP_NET_RAW/CAP_NET_ADMIN).

Only use against networks/devices you own or are explicitly authorized
to assess.
"""

import subprocess
import threading
import time
from typing import Iterable, Optional

from .models import WifiObservation
from .oui import lookup_mac_vendor

# 2.4GHz channels; extend with 5GHz channels (36, 40, 44, ...) if your
# adapter and regulatory domain support them.
DEFAULT_CHANNELS = list(range(1, 12))

WPA_OUI_TYPE1 = b"\x00\x50\xf2\x01"  # Microsoft WPA vendor-specific element


def classify_encryption(pkt) -> str:
    """Best-effort encryption classification from a beacon/probe-response."""
    from scapy.layers.dot11 import Dot11Elt

    cap = pkt.sprintf("{Dot11Beacon:%Dot11Beacon.cap%}{Dot11ProbeResp:%Dot11ProbeResp.cap%}")
    privacy = "privacy" in cap

    has_rsn = False
    has_wpa = False
    elt = pkt.getlayer(Dot11Elt)
    while elt is not None:
        if elt.ID == 48:
            has_rsn = True
        elif elt.ID == 221 and bytes(elt.info[:4]) == WPA_OUI_TYPE1:
            has_wpa = True
        elt = elt.payload.getlayer(Dot11Elt)

    if has_rsn:
        return "WPA2/WPA3"
    if has_wpa:
        return "WPA"
    if privacy:
        return "WEP"
    return "OPEN"


def extract_ssid(pkt) -> Optional[str]:
    from scapy.layers.dot11 import Dot11Elt

    elt = pkt.getlayer(Dot11Elt)
    if elt is not None and elt.ID == 0:
        try:
            ssid = elt.info.decode("utf-8", errors="replace")
        except Exception:
            return None
        return ssid if ssid else None
    return None


def extract_rssi(pkt) -> Optional[int]:
    if hasattr(pkt, "dBm_AntSignal") and pkt.dBm_AntSignal is not None:
        return int(pkt.dBm_AntSignal)
    return None


def extract_channel(pkt) -> Optional[int]:
    from scapy.layers.dot11 import Dot11Elt

    elt = pkt.getlayer(Dot11Elt)
    while elt is not None:
        if elt.ID == 3 and len(elt.info) >= 1:
            return elt.info[0]
        elt = elt.payload.getlayer(Dot11Elt)
    return None


def parse_packet(pkt) -> Optional[WifiObservation]:
    """Turn one captured 802.11 frame into an observation, or None to skip."""
    from scapy.layers.dot11 import Dot11, Dot11Beacon, Dot11ProbeReq, Dot11ProbeResp

    if not pkt.haslayer(Dot11):
        return None
    dot11 = pkt[Dot11]

    if pkt.haslayer(Dot11Beacon):
        return WifiObservation(
            frame_type="beacon",
            bssid=dot11.addr3,
            ssid=extract_ssid(pkt),
            channel=extract_channel(pkt),
            rssi=extract_rssi(pkt),
            encryption=classify_encryption(pkt),
            vendor=lookup_mac_vendor(dot11.addr3),
        )

    if pkt.haslayer(Dot11ProbeResp):
        return WifiObservation(
            frame_type="probe_resp",
            bssid=dot11.addr3,
            client_mac=dot11.addr1,
            ssid=extract_ssid(pkt),
            channel=extract_channel(pkt),
            rssi=extract_rssi(pkt),
            encryption=classify_encryption(pkt),
            vendor=lookup_mac_vendor(dot11.addr3),
        )

    if pkt.haslayer(Dot11ProbeReq):
        return WifiObservation(
            frame_type="probe_req",
            client_mac=dot11.addr2,
            ssid=extract_ssid(pkt),
            rssi=extract_rssi(pkt),
            vendor=lookup_mac_vendor(dot11.addr2),
        )

    if dot11.type == 2:  # data frame -> confirms an active BSSID<->client link
        return WifiObservation(
            frame_type="data",
            bssid=dot11.addr1 if dot11.addr1 else dot11.addr3,
            client_mac=dot11.addr2,
            rssi=extract_rssi(pkt),
            vendor=lookup_mac_vendor(dot11.addr2),
        )

    return None


class ChannelHopper:
    """Cycles a monitor-mode interface across channels in a background thread.

    Hopping maximizes the range of *distinct* networks seen over time
    (any single channel only overlaps a fraction of nearby traffic);
    it does not increase raw radio range, which is bounded by your
    adapter's sensitivity and antenna gain.
    """

    def __init__(self, iface: str, channels: Iterable[int] = DEFAULT_CHANNELS, interval: float = 0.4):
        self.iface = iface
        self.channels = list(channels)
        self.interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            ch = self.channels[i % len(self.channels)]
            subprocess.run(["iw", "dev", self.iface, "set", "channel", str(ch)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            i += 1
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)


def run_wifi_sniffer(iface: str, logger, duration: Optional[float] = None,
                      channels: Iterable[int] = DEFAULT_CHANNELS, hop: bool = True) -> int:
    """Capture on `iface` (must already be in monitor mode), logging each
    parsed observation via `logger.write(...)`. Returns the count logged.
    """
    from scapy.all import sniff

    hopper = ChannelHopper(iface, channels) if hop else None
    if hopper:
        hopper.start()

    count = 0
    start = time.time()

    def _on_packet(pkt):
        nonlocal count
        obs = parse_packet(pkt)
        if obs is not None:
            logger.write(obs)
            count += 1

    def _stop_filter(pkt):
        return duration is not None and (time.time() - start) >= duration

    try:
        sniff(iface=iface, prn=_on_packet, store=False, stop_filter=_stop_filter)
    finally:
        if hopper:
            hopper.stop()

    return count
