"""Lightweight vendor lookups.

Not a full IEEE OUI database (that's 30k+ entries) — just enough common
vendors to make logs readable. Falls back to None when unknown, so it
degrades gracefully rather than lying.
"""

# MAC address OUI (first 3 octets, uppercase, colon-joined) -> vendor name.
_OUI_PREFIXES = {
    "00:1A:11": "Google",
    "3C:5A:B4": "Google",
    "F4:F5:D8": "Google",
    "A4:77:33": "Google",
    "00:17:88": "Philips (Hue)",
    "EC:B5:FA": "Apple",
    "AC:DE:48": "Apple",
    "F0:18:98": "Apple",
    "3C:22:FB": "Apple",
    "DC:A6:32": "Raspberry Pi Foundation",
    "B8:27:EB": "Raspberry Pi Foundation",
    "E4:5F:01": "Raspberry Pi Foundation",
    "28:CD:C1": "Roku",
    "CC:32:E5": "Belkin/Wemo",
    "50:F5:DA": "Samsung",
    "8C:79:F5": "Samsung",
    "A0:CE:C8": "Xiaomi",
    "64:16:66": "Xiaomi",
    "18:FE:34": "Espressif (ESP8266/32)",
    "24:6F:28": "Espressif (ESP8266/32)",
    "3C:71:BF": "Espressif (ESP8266/32)",
    "00:0C:29": "VMware",
    "00:50:56": "VMware",
    "08:00:27": "VirtualBox",
    "00:1B:63": "TP-Link",
    "F4:F2:6D": "TP-Link",
    "00:23:69": "Cisco",
    "00:1D:D8": "Netgear",
}

# BLE Bluetooth SIG company identifiers (little-endian uint16 as seen in
# manufacturer data keys via bleak) -> vendor name. Small common subset.
_BLE_COMPANY_IDS = {
    0x004C: "Apple",
    0x0006: "Microsoft",
    0x00E0: "Google",
    0x0075: "Samsung",
    0x0157: "Xiaomi",
    0x038F: "Xiaomi",
    0x0499: "Ruuvi",
    0x0331: "Espressif",
    0x000F: "Broadcom",
    0x0087: "Garmin",
    0x0002: "Intel",
}


def lookup_mac_vendor(mac: str) -> str | None:
    """Best-effort vendor name for a MAC address, or None if unknown."""
    if not mac or len(mac) < 8:
        return None
    prefix = mac.upper().replace("-", ":")[:8]
    return _OUI_PREFIXES.get(prefix)


def lookup_ble_company(company_id: int) -> str | None:
    """Best-effort vendor name for a BLE company identifier, or None."""
    return _BLE_COMPANY_IDS.get(company_id)


def is_randomized_mac(mac: str) -> bool | None:
    """Whether `mac` has the locally-administered bit set.

    Real vendor-assigned addresses have this bit (the second-least-
    significant bit of the first octet) clear. Modern phones/OSes set it
    when generating a private address (WiFi probe-request randomization,
    BLE private addresses), so a set bit means the address isn't a stable
    per-device identifier and any OUI vendor lookup on it is meaningless.
    Returns None if `mac` isn't parseable.
    """
    if not mac or len(mac) < 2:
        return None
    first_octet = mac.upper().replace("-", ":").split(":", 1)[0]
    try:
        value = int(first_octet, 16)
    except ValueError:
        return None
    return bool(value & 0x02)
