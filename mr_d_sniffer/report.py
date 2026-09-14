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

    connections = defaultdict(lambda: {"count": 0, "vendor": None, "best_rssi": None})
    for r in wifi:
        if r.get("frame_type") != "data":
            continue
        bssid, client = r.get("bssid"), r.get("client_mac")
        if not bssid or not client:
            continue
        conn = connections[(bssid, client)]
        conn["count"] += 1
        if r.get("vendor"):
            conn["vendor"] = r["vendor"]
        if r.get("rssi") is not None:
            conn["best_rssi"] = r["rssi"] if conn["best_rssi"] is None else max(conn["best_rssi"], r["rssi"])

    connected_clients = [
        {"bssid": bssid, "client_mac": client, "ssids": sorted(aps[bssid]["ssids"]) if bssid in aps else [],
         "vendor": info["vendor"], "best_rssi": info["best_rssi"], "count": info["count"]}
        for (bssid, client), info in sorted(connections.items(), key=lambda kv: -kv[1]["count"])
    ]

    return {
        "total_records": len(records),
        "first_seen": timestamps[0] if timestamps else None,
        "last_seen": timestamps[-1] if timestamps else None,
        "wifi_frame_count": len(wifi),
        "ble_frame_count": len(ble),
        "access_points": dict(aps),
        "wifi_clients": dict(clients),
        "ble_devices": dict(devices),
        "connected_clients": connected_clients,
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

    connected = summary.get("connected_clients") or []
    if connected:
        lines.append(f"## Connected Clients ({len(connected)} AP&ndash;client associations)")
        lines.append("")
        lines.append("| BSSID | SSID(s) | Client MAC | Vendor | Best RSSI | Frames |")
        lines.append("|---|---|---|---|---|---|")
        for conn in connected:
            ssids = ", ".join(conn["ssids"]) or "(unknown)"
            vendor = conn["vendor"] or "?"
            rssi = conn["best_rssi"] if conn["best_rssi"] is not None else "?"
            lines.append(f"| {conn['bssid']} | {ssids} | {conn['client_mac']} | {vendor} | {rssi} | {conn['count']} |")
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


def _rssi_pct(rssi) -> int:
    """Map dBm (~-30 strong to ~-100 weak) to a 0-100% bar width."""
    if rssi is None:
        return 0
    return max(0, min(100, round((rssi + 100) / 70 * 100)))


def _html_escape(value) -> str:
    text = "" if value is None else str(value)
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _signal_cell(rssi) -> str:
    if rssi is None:
        return "?"
    pct = _rssi_pct(rssi)
    return (
        f'<div class="sig"><div class="sig-track"><div class="sig-fill" style="width:{pct}%"></div></div>'
        f"<span>{rssi} dBm</span></div>"
    )


def _ap_rows_html(aps: dict) -> str:
    rows = []
    for bssid, info in sorted(aps.items(), key=lambda kv: -kv[1]["count"]):
        ssids = _html_escape(", ".join(sorted(info["ssids"])) or "(hidden)")
        channels = _html_escape(", ".join(str(c) for c in sorted(info["channels"])))
        enc = _html_escape(", ".join(sorted(info["encryption"])) or "?")
        vendor = _html_escape(info["vendor"] or "?")
        rows.append(
            f"<tr><td>{_html_escape(bssid)}</td><td>{ssids}</td><td>{channels}</td>"
            f"<td>{enc}</td><td>{vendor}</td><td>{_signal_cell(info['best_rssi'])}</td>"
            f"<td>{info['count']}</td></tr>"
        )
    return "".join(rows)


def _client_rows_html(clients: dict) -> str:
    rows = []
    for mac, info in sorted(clients.items(), key=lambda kv: -kv[1]["count"]):
        ssids = _html_escape(", ".join(sorted(info["ssids_probed"])) or "(broadcast)")
        rows.append(
            f"<tr><td>{_html_escape(mac)}</td><td>{ssids}</td>"
            f"<td>{_signal_cell(info['best_rssi'])}</td><td>{info['count']}</td></tr>"
        )
    return "".join(rows)


def _connection_rows_html(connections: list) -> str:
    rows = []
    for conn in connections:
        ssids = _html_escape(", ".join(conn["ssids"]) or "(unknown)")
        vendor = _html_escape(conn["vendor"] or "?")
        rows.append(
            f"<tr><td>{_html_escape(conn['bssid'])}</td><td>{ssids}</td>"
            f"<td>{_html_escape(conn['client_mac'])}</td><td>{vendor}</td>"
            f"<td>{_signal_cell(conn['best_rssi'])}</td><td>{conn['count']}</td></tr>"
        )
    return "".join(rows)


def _ble_rows_html(devices: dict) -> str:
    rows = []
    for addr, info in sorted(devices.items(), key=lambda kv: -kv[1]["count"]):
        name = _html_escape(info["name"] or "?")
        vendor = _html_escape(info["vendor"] or "?")
        rows.append(
            f"<tr><td>{_html_escape(addr)}</td><td>{name}</td><td>{vendor}</td>"
            f"<td>{_signal_cell(info['best_rssi'])}</td><td>{info['count']}</td></tr>"
        )
    return "".join(rows)


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Mr D Sniffer - Session Report</title>
<style>
  :root {{ color-scheme: light dark; }}
  html {{ background: #fdf3ff; }}
  @media (prefers-color-scheme: dark) {{ html {{ background: #1a1522; }} }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 1100px; margin: 0 auto; padding: 0 16px 24px; line-height: 1.5;
         background: radial-gradient(circle at 15% 0%, rgba(106,61,245,.15), transparent 45%),
                     radial-gradient(circle at 85% 15%, rgba(213,48,154,.14), transparent 45%),
                     radial-gradient(circle at 50% 100%, rgba(255,122,61,.12), transparent 50%); }}
  .banner {{
    margin: 0 -16px 20px; padding: 22px 16px 26px;
    background: linear-gradient(120deg, #6a3df5, #d5309a 45%, #ff7a3d 85%);
    color: #fff; border-radius: 0 0 18px 18px;
  }}
  .banner h1 {{ margin: 0 0 2px; font-size: 1.6em; }}
  .banner .muted {{ opacity: .92; }}
  .muted {{ opacity: .65; font-size: .9em; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 16px 0; }}
  .card {{ border-radius: 12px; padding: 14px; color: #fff; }}
  .card .n {{ font-size: 1.7em; font-weight: 700; display: block; }}
  .card-total {{ background: linear-gradient(135deg, #3a86ff, #2667cc); }}
  .card-ap {{ background: linear-gradient(135deg, #58a6ff, #2f6fd6); }}
  .card-client {{ background: linear-gradient(135deg, #ffa657, #e8722c); }}
  .card-conn {{ background: linear-gradient(135deg, #d2a8ff, #9b5de5); }}
  .card-ble {{ background: linear-gradient(135deg, #7ee787, #2f9e44); }}
  table {{ border-collapse: collapse; width: 100%; margin: 8px 0 28px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid rgba(128,128,128,.3); }}
  th {{ cursor: pointer; user-select: none; white-space: nowrap; }}
  th:hover {{ opacity: .7; }}
  th.sorted::after {{ content: " \\25BE"; }}
  .sig {{ display: flex; align-items: center; gap: 8px; min-width: 140px; }}
  .sig-track {{ flex: 1; background: rgba(128,128,128,.2); border-radius: 4px; height: 10px; overflow: hidden; }}
  .sig-fill {{ background: #2f9e44; height: 100%; }}
  .sig span {{ font-size: .85em; opacity: .8; white-space: nowrap; }}
  input[type="search"] {{ padding: 8px 10px; border-radius: 8px; border: 1px solid currentColor;
                          background: transparent; color: inherit; width: 100%; max-width: 320px; margin-bottom: 8px; }}
  section {{ margin-bottom: 36px; }}
  .empty {{ opacity: .6; font-style: italic; }}
</style>
</head>
<body>
<div class="banner">
  <h1>🛰️ Mr D Sniffer</h1>
  <p class="muted">Source: {source} &middot; Generated: {generated} &middot; Range: {first_seen} &rarr; {last_seen}</p>
</div>

<section class="grid">
  <div class="card card-total"><span class="n">{total_records}</span>Total records</div>
  <div class="card card-ap"><span class="n">{ap_count}</span>Access points</div>
  <div class="card card-client"><span class="n">{client_count}</span>Probing clients</div>
  <div class="card card-conn"><span class="n">{conn_count}</span>Connected clients</div>
  <div class="card card-ble"><span class="n">{ble_count}</span>BLE devices</div>
</section>

<section>
<h2>WiFi Access Points</h2>
<input type="search" data-filter-for="ap-table" placeholder="Filter by BSSID, SSID, vendor...">
{ap_table}
</section>

<section>
<h2>WiFi Probing Clients</h2>
<input type="search" data-filter-for="client-table" placeholder="Filter by MAC or SSID...">
{client_table}
</section>

<section>
<h2>Connected Clients</h2>
<p class="muted">Devices seen actively associated with an access point (from 802.11 data frames), not just probing for one.</p>
<input type="search" data-filter-for="conn-table" placeholder="Filter by BSSID, SSID, client MAC, vendor...">
{conn_table}
</section>

<section>
<h2>BLE Devices</h2>
<input type="search" data-filter-for="ble-table" placeholder="Filter by address, name, vendor...">
{ble_table}
</section>

<script>
// Click-to-sort and live filtering; no external libraries, works offline.
function sortTable(table, col, numeric) {{
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const dir = table.dataset.sortCol == col && table.dataset.sortDir == "asc" ? "desc" : "asc";
  rows.sort((a, b) => {{
    let x = a.cells[col].textContent.trim();
    let y = b.cells[col].textContent.trim();
    if (numeric) {{ x = parseFloat(x) || -9999; y = parseFloat(y) || -9999; }}
    if (x < y) return dir === "asc" ? -1 : 1;
    if (x > y) return dir === "asc" ? 1 : -1;
    return 0;
  }});
  rows.forEach(r => tbody.appendChild(r));
  table.dataset.sortCol = col;
  table.dataset.sortDir = dir;
  table.querySelectorAll("th").forEach(th => th.classList.remove("sorted"));
  table.tHead.rows[0].cells[col].classList.add("sorted");
}}

document.querySelectorAll("table").forEach(table => {{
  const headers = table.tHead ? table.tHead.rows[0].cells : [];
  Array.from(headers).forEach((th, i) => {{
    th.addEventListener("click", () => sortTable(table, i, th.dataset.numeric === "1"));
  }});
}});

document.querySelectorAll("input[data-filter-for]").forEach(input => {{
  const table = document.getElementById(input.dataset.filterFor);
  if (!table) return;
  input.addEventListener("input", () => {{
    const q = input.value.toLowerCase();
    Array.from(table.tBodies[0].rows).forEach(row => {{
      row.style.display = row.textContent.toLowerCase().includes(q) ? "" : "none";
    }});
  }});
}});
</script>

</body>
</html>
"""


def render_html(summary: dict, source_path: str) -> str:
    aps = summary["access_points"]
    clients = summary["wifi_clients"]
    devices = summary["ble_devices"]
    connections = summary.get("connected_clients") or []

    def _table(table_id, headers, numeric_cols, rows_html, empty_msg):
        if not rows_html:
            return f'<p class="empty">{empty_msg}</p>'
        ths = "".join(
            f'<th data-numeric="{"1" if i in numeric_cols else "0"}">{h}</th>' for i, h in enumerate(headers)
        )
        return f'<table id="{table_id}"><thead><tr>{ths}</tr></thead><tbody>{rows_html}</tbody></table>'

    ap_table = _table(
        "ap-table", ["BSSID", "SSID(s)", "Channel(s)", "Encryption", "Vendor", "Best RSSI", "Frames"],
        {6}, _ap_rows_html(aps), "No WiFi access points captured.",
    )
    client_table = _table(
        "client-table", ["Client MAC", "SSIDs Probed", "Best RSSI", "Frames"],
        {3}, _client_rows_html(clients), "No probing WiFi clients captured.",
    )
    conn_table = _table(
        "conn-table", ["BSSID", "SSID(s)", "Client MAC", "Vendor", "Best RSSI", "Frames"],
        {5}, _connection_rows_html(connections), "No connected clients captured yet.",
    )
    ble_table = _table(
        "ble-table", ["Address", "Name", "Vendor", "Best RSSI", "Advertisements"],
        {4}, _ble_rows_html(devices), "No BLE devices captured.",
    )

    return _HTML_TEMPLATE.format(
        source=_html_escape(os.path.basename(source_path)),
        generated=datetime.now(timezone.utc).isoformat(),
        first_seen=_html_escape(summary["first_seen"] or "n/a"),
        last_seen=_html_escape(summary["last_seen"] or "n/a"),
        total_records=summary["total_records"],
        ap_count=len(aps),
        client_count=len(clients),
        conn_count=len(connections),
        ble_count=len(devices),
        ap_table=ap_table,
        client_table=client_table,
        conn_table=conn_table,
        ble_table=ble_table,
    )


def write_html_report(jsonl_path: str, out_path: str) -> str:
    records = list(read_jsonl(jsonl_path))
    summary = summarize(records)
    html = render_html(summary, jsonl_path)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path
