"""Turn a raw JSONL capture session into a readable markdown summary."""

import os
from collections import defaultdict
from datetime import datetime, timezone

from .logger import read_jsonl


def _is_wifi(rec: dict) -> bool:
    return "frame_type" in rec


def _is_ble(rec: dict) -> bool:
    return "address" in rec and "frame_type" not in rec


def summarize(records: list[dict]) -> dict:
    wifi = [r for r in records if _is_wifi(r)]
    ble = [r for r in records if _is_ble(r)]

    timestamps = sorted(r.get("timestamp", "") for r in records if r.get("timestamp"))

    aps = defaultdict(lambda: {"count": 0, "ssids": set(), "channels": set(),
                                "best_rssi": None, "vendor": None, "encryption": set()})
    clients = defaultdict(lambda: {"count": 0, "ssids_probed": set(), "best_rssi": None})

    for r in wifi:
        bssid = r.get("bssid")
        if bssid:
            ap = aps[bssid]
            ap["count"] += 1
            if r.get("ssid"):
                ap["ssids"].add(r["ssid"])
            if r.get("channel") is not None:
                ap["channels"].add(r["channel"])
            if r.get("encryption"):
                ap["encryption"].add(r["encryption"])
            if r.get("vendor"):
                ap["vendor"] = r["vendor"]
            if r.get("rssi") is not None:
                ap["best_rssi"] = r["rssi"] if ap["best_rssi"] is None else max(ap["best_rssi"], r["rssi"])

        client = r.get("client_mac")
        if client and r.get("frame_type") == "probe_req":
            c = clients[client]
            c["count"] += 1
            if r.get("ssid"):
                c["ssids_probed"].add(r["ssid"])
            if r.get("rssi") is not None:
                c["best_rssi"] = r["rssi"] if c["best_rssi"] is None else max(c["best_rssi"], r["rssi"])

    devices = defaultdict(lambda: {"count": 0, "name": None, "vendor": None, "best_rssi": None})
    for r in ble:
        addr = r["address"]
        d = devices[addr]
        d["count"] += 1
        if r.get("name"):
            d["name"] = r["name"]
        if r.get("vendor"):
            d["vendor"] = r["vendor"]
        if r.get("rssi") is not None:
            d["best_rssi"] = r["rssi"] if d["best_rssi"] is None else max(d["best_rssi"], r["rssi"])

    return {
        "total_records": len(records),
        "first_seen": timestamps[0] if timestamps else None,
        "last_seen": timestamps[-1] if timestamps else None,
        "wifi_frame_count": len(wifi),
        "ble_frame_count": len(ble),
        "access_points": dict(aps),
        "wifi_clients": dict(clients),
        "ble_devices": dict(devices),
    }


def render_markdown(summary: dict, source_path: str) -> str:
    lines = []
    lines.append(f"# RF Recon Session Report")
    lines.append("")
    lines.append(f"- Source log: `{os.path.basename(source_path)}`")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Total records: {summary['total_records']}")
    lines.append(f"- Time range: {summary['first_seen']} -> {summary['last_seen']}")
    lines.append("")

    aps = summary["access_points"]
    if aps:
        lines.append(f"## WiFi Access Points ({len(aps)} unique BSSIDs)")
        lines.append("")
        lines.append("| BSSID | SSID(s) | Channel(s) | Encryption | Vendor | Best RSSI | Frames |")
        lines.append("|---|---|---|---|---|---|---|")
        for bssid, info in sorted(aps.items(), key=lambda kv: -kv[1]["count"]):
            ssids = ", ".join(sorted(info["ssids"])) or "(hidden)"
            channels = ", ".join(str(c) for c in sorted(info["channels"]))
            enc = ", ".join(sorted(info["encryption"])) or "?"
            vendor = info["vendor"] or "?"
            rssi = info["best_rssi"] if info["best_rssi"] is not None else "?"
            lines.append(f"| {bssid} | {ssids} | {channels} | {enc} | {vendor} | {rssi} | {info['count']} |")
        lines.append("")

    clients = summary["wifi_clients"]
    if clients:
        lines.append(f"## WiFi Probing Clients ({len(clients)} unique MACs)")
        lines.append("")
        lines.append("| Client MAC | SSIDs Probed | Best RSSI | Frames |")
        lines.append("|---|---|---|---|")
        for mac, info in sorted(clients.items(), key=lambda kv: -kv[1]["count"]):
            ssids = ", ".join(sorted(info["ssids_probed"])) or "(broadcast)"
            rssi = info["best_rssi"] if info["best_rssi"] is not None else "?"
            lines.append(f"| {mac} | {ssids} | {rssi} | {info['count']} |")
        lines.append("")

    devices = summary["ble_devices"]
    if devices:
        lines.append(f"## BLE Devices ({len(devices)} unique addresses)")
        lines.append("")
        lines.append("| Address | Name | Vendor | Best RSSI | Advertisements |")
        lines.append("|---|---|---|---|---|")
        for addr, info in sorted(devices.items(), key=lambda kv: -kv[1]["count"]):
            name = info["name"] or "?"
            vendor = info["vendor"] or "?"
            rssi = info["best_rssi"] if info["best_rssi"] is not None else "?"
            lines.append(f"| {addr} | {name} | {vendor} | {rssi} | {info['count']} |")
        lines.append("")

    return "\n".join(lines)


def write_report(jsonl_path: str, out_path: str) -> str:
    records = list(read_jsonl(jsonl_path))
    summary = summarize(records)
    markdown = render_markdown(summary, jsonl_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    return out_path
