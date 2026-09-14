"""Live-updating HTTP dashboard for an in-progress (or finished) capture.

Unlike `report --html` (a one-shot static snapshot), this starts a small
HTTP server that re-reads the JSONL log on every poll from the browser,
so the page keeps updating while a `wifi`/`ble`/`both` capture is still
appending to the same file. Stdlib only - no extra dependencies.
"""

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .report import _html_escape, summarize


MAX_EVENT_BACKLOG = 500  # cap on how many past events /api/events will ever send in one response


def _read_records_lenient(path: str) -> list[dict]:
    """Like logger.read_jsonl, but tolerates a partially-written final line
    (the capture process may be mid-append when we read)."""
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def _jsonable_group(group: dict) -> dict:
    out = {}
    for key, info in group.items():
        entry = dict(info)
        for field, value in entry.items():
            if isinstance(value, set):
                entry[field] = sorted(value)
        out[key] = entry
    return out


def summary_to_json(summary: dict) -> dict:
    return {
        "total_records": summary["total_records"],
        "first_seen": summary["first_seen"],
        "last_seen": summary["last_seen"],
        "wifi_frame_count": summary["wifi_frame_count"],
        "ble_frame_count": summary["ble_frame_count"],
        "access_points": _jsonable_group(summary["access_points"]),
        "wifi_clients": _jsonable_group(summary["wifi_clients"]),
        "ble_devices": _jsonable_group(summary["ble_devices"]),
        "connected_clients": summary.get("connected_clients") or [],
    }


def _make_handler(jsonl_path: str, interval: float, scan_state: Optional[dict]):
    html_body = _LIVE_HTML_TEMPLATE.replace(
        "__INTERVAL_MS__", str(int(interval * 1000))
    ).replace(
        "__SOURCE__", _html_escape(os.path.basename(jsonl_path))
    ).replace(
        "__SCAN_ENABLED__", "true" if scan_state is not None else "false"
    ).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # keep the console quiet during a capture

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", html_body)
            elif self.path.startswith("/api/summary"):
                self._serve_summary()
            elif self.path.startswith("/api/events"):
                self._serve_events()
            elif self.path.startswith("/api/scan"):
                self._serve_scan()
            else:
                self.send_error(404)

        def _serve_summary(self):
            try:
                records = _read_records_lenient(jsonl_path)
                payload = json.dumps(summary_to_json(summarize(records))).encode("utf-8")
                self._send(200, "application/json; charset=utf-8", payload)
            except FileNotFoundError:
                payload = json.dumps({"error": f"log not found: {jsonl_path}"}).encode("utf-8")
                self._send(404, "application/json; charset=utf-8", payload)

        def _serve_events(self):
            from urllib.parse import parse_qs, urlsplit

            since = int(parse_qs(urlsplit(self.path).query).get("since", ["0"])[0])
            try:
                records = _read_records_lenient(jsonl_path)
            except FileNotFoundError:
                records = []
            # Safety cap: never send more than the most recent MAX_BACKLOG
            # records in one response, even if a client's `since` is very
            # stale (e.g. a tab left open across a huge capture) - avoids a
            # multi-MB payload that can lock up the browser tab.
            since = max(since, len(records) - MAX_EVENT_BACKLOG)
            new_records = records[since:] if since < len(records) else []
            payload = json.dumps({"events": new_records, "total": len(records)}).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)

        def _serve_scan(self):
            if scan_state is None:
                payload = json.dumps({"enabled": False, "results": {}}).encode("utf-8")
            else:
                with scan_state["lock"]:
                    payload = json.dumps({"enabled": True, "results": scan_state["results"]}).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)

        def _send(self, status: int, content_type: str, body: bytes):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _scan_loop(jsonl_path: str, scan_state: dict, interval: float = 20.0) -> None:
    from .portscan import scan_many

    while not scan_state["stop"].is_set():
        try:
            records = _read_records_lenient(jsonl_path)
            summary = summarize(records)
            ips = sorted({c["ip_address"] for c in summary.get("connected_clients", []) if c.get("ip_address")})
            if ips:
                results = scan_many(ips)
                with scan_state["lock"]:
                    scan_state["results"].update(results)
        except FileNotFoundError:
            pass
        scan_state["stop"].wait(interval)


def run_live_server(jsonl_path: str, port: int, interval: float = 2.0, open_browser: bool = False,
                     scan_ports: bool = False) -> None:
    scan_state = None
    scan_thread = None
    if scan_ports:
        scan_state = {"lock": threading.Lock(), "results": {}, "stop": threading.Event()}
        scan_thread = threading.Thread(target=_scan_loop, args=(jsonl_path, scan_state), daemon=True)
        scan_thread.start()
        print("[live] active port scanning ENABLED for devices with a known IP - "
              "only use against devices you own or are authorized to test")

    handler = _make_handler(jsonl_path, interval, scan_state)
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    url = f"http://localhost:{port}/"
    print(f"[live] serving {jsonl_path}")
    print(f"[live] open {url} (or http://<this-machine's-hostname-or-IP>:{port}/ from another device)")
    print("[live] Ctrl-C to stop")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[live] stopped.")
    finally:
        server.server_close()
        if scan_state is not None:
            scan_state["stop"].set()


_LIVE_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RF Recon - Live</title>
<style>
  :root { color-scheme: dark; }
  html { background: #14101c; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 1100px; margin: 0 auto; padding: 0 16px 24px; line-height: 1.5;
         color: #e8e6ef;
         background: radial-gradient(circle at 15% 0%, rgba(106,61,245,.28), transparent 45%),
                     radial-gradient(circle at 85% 15%, rgba(213,48,154,.24), transparent 45%),
                     radial-gradient(circle at 50% 100%, rgba(255,122,61,.18), transparent 50%); }
  .banner {
    margin: 0 -16px 20px; padding: 22px 16px 26px;
    background: linear-gradient(120deg, #6a3df5, #d5309a 45%, #ff7a3d 85%);
    color: #fff; border-radius: 0 0 18px 18px;
  }
  .banner h1 { margin: 0 0 2px; display: flex; align-items: center; gap: 10px; font-size: 1.6em; }
  .banner .sub { opacity: .92; font-size: .85em; }
  .banner .sub b { font-weight: 700; }
  #status { font-size: .7em; padding: 3px 9px; border-radius: 999px; font-weight: 600; background: rgba(255,255,255,.22); }
  #status.err { background: rgba(0,0,0,.35); }
  #sound-toggle {
    font: inherit; font-size: .75em; cursor: pointer; border: 1px solid rgba(255,255,255,.6);
    background: rgba(255,255,255,.15); color: #fff; border-radius: 999px; padding: 4px 12px; margin-left: auto;
  }
  #sound-toggle:hover { background: rgba(255,255,255,.28); }
  .muted { opacity: .65; font-size: .9em; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 16px 0; }
  .card { border-radius: 12px; padding: 14px; color: #fff; }
  .card .n { font-size: 1.7em; font-weight: 700; display: block; }
  .card-total { background: linear-gradient(135deg, #3a86ff, #2667cc); }
  .card-ap { background: linear-gradient(135deg, #58a6ff, #2f6fd6); }
  .card-client { background: linear-gradient(135deg, #ffa657, #e8722c); }
  .card-conn { background: linear-gradient(135deg, #d2a8ff, #9b5de5); }
  .card-ble { background: linear-gradient(135deg, #7ee787, #2f9e44); }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 28px; display: block; overflow-x: auto; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid rgba(128,128,128,.3); }
  th { cursor: pointer; user-select: none; white-space: nowrap; }
  th:hover { opacity: .7; }
  th.sorted::after { content: " \\25BE"; }
  .sig { display: flex; align-items: center; gap: 8px; min-width: 140px; }
  .sig-track { flex: 1; background: rgba(128,128,128,.2); border-radius: 4px; height: 10px; overflow: hidden; }
  .sig-fill { background: #2f9e44; height: 100%; }
  .sig span { font-size: .85em; opacity: .8; white-space: nowrap; }
  input[type="search"] { padding: 8px 10px; border-radius: 8px; border: 1px solid currentColor;
                          background: transparent; color: inherit; width: 100%; max-width: 320px; margin-bottom: 8px; }
  section { margin-bottom: 36px; }
  .empty td { opacity: .6; font-style: italic; }

  .feed-wrap { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
  @media (max-width: 900px) { .feed-wrap { grid-template-columns: 1fr; } }
  .feed-panel {
    background: #0d1117; border-radius: 10px; padding: 10px 12px;
    font-family: "SF Mono", Consolas, "Courier New", monospace;
    font-size: 12.5px; line-height: 1.55;
  }
  .feed-panel h3 { margin: 0 0 8px; font-family: -apple-system, sans-serif; font-size: 13px;
                    color: #8b949e; text-transform: uppercase; letter-spacing: .04em; }
  .feed-panel > div[id^="feed-"] { height: 300px; overflow-y: auto; }
  .feed-line { white-space: pre-wrap; word-break: break-all; animation: feedIn .25s ease-out; padding: 1px 0; }
  @keyframes feedIn { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: none; } }
  .feed-ts { color: #6e7681; }
  .ft-beacon { color: #58a6ff; }
  .ft-probe_req { color: #ffa657; }
  .ft-probe_resp { color: #d2a8ff; }
  .ft-data { color: #8b949e; }
  .ft-ble { color: #7ee787; }
  .feed-empty { color: #6e7681; font-style: italic; }
</style>
</head>
<body>
<div class="banner">
  <h1>🛰️ Mr D Sniffer <span id="status" class="ok">Connecting...</span>
      <button id="sound-toggle" type="button">🔇 Sound: Off</button></h1>
  <div class="sub">Live RF Recon Dashboard &middot; Source: <b>__SOURCE__</b> &middot; <span id="meta">waiting for first update...</span></div>
</div>

<section class="grid">
  <div class="card card-total"><span class="n" id="stat-total">0</span>Total records</div>
  <div class="card card-ap"><span class="n" id="stat-ap">0</span>Access points</div>
  <div class="card card-client"><span class="n" id="stat-client">0</span>Probing clients</div>
  <div class="card card-conn"><span class="n" id="stat-conn">0</span>Connected clients</div>
  <div class="card card-ble"><span class="n" id="stat-ble">0</span>BLE devices</div>
</section>

<section>
<h2>Live Event Feed</h2>
<div class="feed-wrap">
  <div class="feed-panel"><h3>WiFi</h3><div id="feed-wifi"><div class="feed-empty">Waiting for beacons/probes...</div></div></div>
  <div class="feed-panel"><h3>Connected Clients</h3><div id="feed-conn"><div class="feed-empty">Waiting for data frames...</div></div></div>
  <div class="feed-panel"><h3>BLE</h3><div id="feed-ble"><div class="feed-empty">Waiting for BLE advertisements...</div></div></div>
</div>
</section>

<section>
<h2>WiFi Access Points</h2>
<input type="search" data-filter-for="ap-table" placeholder="Filter by BSSID, SSID, vendor...">
<table id="ap-table">
<thead><tr>
<th data-numeric="0">BSSID</th><th data-numeric="0">SSID(s)</th><th data-numeric="0">Channel(s)</th>
<th data-numeric="0">Encryption</th><th data-numeric="0">Vendor</th><th data-numeric="1">Best RSSI</th><th data-numeric="1">Frames</th>
<th data-numeric="0">First Seen</th><th data-numeric="0">Last Seen</th>
</tr></thead>
<tbody></tbody>
</table>
</section>

<section>
<h2>WiFi Probing Clients</h2>
<input type="search" data-filter-for="client-table" placeholder="Filter by MAC or SSID...">
<table id="client-table">
<thead><tr><th data-numeric="0">Client MAC</th><th data-numeric="0">Name</th><th data-numeric="0">SSIDs Probed</th><th data-numeric="1">Best RSSI</th><th data-numeric="1">Frames</th><th data-numeric="0">First Seen</th><th data-numeric="0">Last Seen</th></tr></thead>
<tbody></tbody>
</table>
</section>

<section>
<h2>Connected Clients</h2>
<p class="muted">Devices actively associated with an access point (from 802.11 data frames), not just probing for one.</p>
<input type="search" data-filter-for="conn-table" placeholder="Filter by BSSID, SSID, client MAC, vendor...">
<table id="conn-table">
<thead><tr><th data-numeric="0">BSSID</th><th data-numeric="0">SSID(s)</th><th data-numeric="0">Client MAC</th><th data-numeric="0">Name</th><th data-numeric="0">IP Address</th><th data-numeric="0">Vendor</th><th data-numeric="1">Best RSSI</th><th data-numeric="1">Frames</th><th data-numeric="0">First Seen</th><th data-numeric="0">Last Seen</th></tr></thead>
<tbody></tbody>
</table>
</section>

<section id="scan-section">
<h2>Open Services (Active Scan) <span class="muted" style="font-size:.6em;">- transmits to each device, unlike everything else here</span></h2>
<p class="muted" id="scan-status">Checking scan status...</p>
<input type="search" data-filter-for="scan-table" placeholder="Filter by IP or service...">
<table id="scan-table">
<thead><tr><th data-numeric="0">IP Address</th><th data-numeric="0">Open Ports / Services</th><th data-numeric="0">Last Scanned</th></tr></thead>
<tbody></tbody>
</table>
</section>

<section>
<h2>BLE Devices</h2>
<input type="search" data-filter-for="ble-table" placeholder="Filter by address, name, vendor...">
<table id="ble-table">
<thead><tr><th data-numeric="0">Address</th><th data-numeric="0">Name</th><th data-numeric="0">Vendor</th><th data-numeric="1">Best RSSI</th><th data-numeric="1">Advertisements</th><th data-numeric="0">First Seen</th><th data-numeric="0">Last Seen</th></tr></thead>
<tbody></tbody>
</table>
</section>

<script>
const POLL_MS = __INTERVAL_MS__;
const SCAN_ENABLED = __SCAN_ENABLED__;
const sortState = {};
const filterState = {};

function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
}

function sigCell(rssi) {
  if (rssi === null || rssi === undefined) return "?";
  const pct = Math.max(0, Math.min(100, Math.round((rssi + 100) / 70 * 100)));
  return `<div class="sig"><div class="sig-track"><div class="sig-fill" style="width:${pct}%"></div></div><span>${rssi} dBm</span></div>`;
}

function emptyRow(colspan, msg) {
  return `<tr class="empty"><td colspan="${colspan}">${msg}</td></tr>`;
}

function fmtTs(ts) {
  return ts ? String(ts).replace("T", " ").slice(0, 19) : "?";
}

function seenCells(info) {
  return `<td>${esc(fmtTs(info.first_seen))}</td><td>${esc(fmtTs(info.last_seen))}</td>`;
}

function buildApRows(aps) {
  const entries = Object.entries(aps).sort((a, b) => b[1].count - a[1].count);
  if (!entries.length) return emptyRow(9, "No WiFi access points captured yet.");
  return entries.map(([bssid, info]) => {
    const ssids = (info.ssids && info.ssids.length) ? info.ssids.join(", ") : "(hidden)";
    const channels = (info.channels || []).join(", ");
    const enc = (info.encryption && info.encryption.length) ? info.encryption.join(", ") : "?";
    return `<tr><td>${esc(bssid)}</td><td>${esc(ssids)}</td><td>${esc(channels)}</td>` +
           `<td>${esc(enc)}</td><td>${esc(info.vendor || "?")}</td>` +
           `<td>${sigCell(info.best_rssi)}</td><td>${info.count}</td>${seenCells(info)}</tr>`;
  }).join("");
}

function buildClientRows(clients) {
  const entries = Object.entries(clients).sort((a, b) => b[1].count - a[1].count);
  if (!entries.length) return emptyRow(7, "No probing WiFi clients captured yet.");
  return entries.map(([mac, info]) => {
    const ssids = (info.ssids_probed && info.ssids_probed.length) ? info.ssids_probed.join(", ") : "(broadcast)";
    return `<tr><td>${esc(mac)}</td><td>${esc(info.name || "?")}</td><td>${esc(ssids)}</td>` +
           `<td>${sigCell(info.best_rssi)}</td><td>${info.count}</td>${seenCells(info)}</tr>`;
  }).join("");
}

function buildConnRows(connections) {
  if (!connections.length) return emptyRow(10, "No connected clients captured yet.");
  return connections.map(conn => {
    const ssids = (conn.ssids && conn.ssids.length) ? conn.ssids.join(", ") : "(unknown)";
    return `<tr><td>${esc(conn.bssid)}</td><td>${esc(ssids)}</td><td>${esc(conn.client_mac)}</td>` +
           `<td>${esc(conn.name || "?")}</td><td>${esc(conn.ip_address || "?")}</td><td>${esc(conn.vendor || "?")}</td>` +
           `<td>${sigCell(conn.best_rssi)}</td><td>${conn.count}</td>${seenCells(conn)}</tr>`;
  }).join("");
}

function buildBleRows(devices) {
  const entries = Object.entries(devices).sort((a, b) => b[1].count - a[1].count);
  if (!entries.length) return emptyRow(7, "No BLE devices captured yet.");
  return entries.map(([addr, info]) => {
    return `<tr><td>${esc(addr)}</td><td>${esc(info.name || "?")}</td><td>${esc(info.vendor || "?")}</td>` +
           `<td>${sigCell(info.best_rssi)}</td><td>${info.count}</td>${seenCells(info)}</tr>`;
  }).join("");
}

function sortRows(table, col, numeric, dir) {
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows).filter(r => !r.classList.contains("empty"));
  rows.sort((a, b) => {
    let x = a.cells[col].textContent.trim();
    let y = b.cells[col].textContent.trim();
    if (numeric) { x = parseFloat(x); y = parseFloat(y); x = isNaN(x) ? -9999 : x; y = isNaN(y) ? -9999 : y; }
    if (x < y) return dir === "asc" ? -1 : 1;
    if (x > y) return dir === "asc" ? 1 : -1;
    return 0;
  });
  rows.forEach(r => tbody.appendChild(r));
}

document.querySelectorAll("table").forEach(table => {
  const headers = table.tHead ? table.tHead.rows[0].cells : [];
  Array.from(headers).forEach((th, i) => {
    th.addEventListener("click", () => {
      const st = sortState[table.id] || {};
      const dir = st.col === i && st.dir === "asc" ? "desc" : "asc";
      sortState[table.id] = { col: i, dir, numeric: th.dataset.numeric === "1" };
      sortRows(table, i, th.dataset.numeric === "1", dir);
      table.querySelectorAll("th").forEach(h => h.classList.remove("sorted"));
      th.classList.add("sorted");
    });
  });
});

function reapplySort(tableId) {
  const st = sortState[tableId];
  if (!st) return;
  sortRows(document.getElementById(tableId), st.col, st.numeric, st.dir);
}

document.querySelectorAll("input[data-filter-for]").forEach(input => {
  const id = input.dataset.filterFor;
  input.addEventListener("input", () => { filterState[id] = input.value.toLowerCase(); applyFilter(id); });
});

function applyFilter(tableId) {
  const q = filterState[tableId] || "";
  const table = document.getElementById(tableId);
  if (!table) return;
  Array.from(table.tBodies[0].rows).forEach(row => {
    if (row.classList.contains("empty")) return;
    row.style.display = row.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

function render(data) {
  if (eventsSince === null) eventsSince = data.total_records; // start the live feed from "now", not the whole backlog
  document.getElementById("stat-total").textContent = data.total_records;
  document.getElementById("stat-ap").textContent = Object.keys(data.access_points).length;
  document.getElementById("stat-client").textContent = Object.keys(data.wifi_clients).length;
  document.getElementById("stat-conn").textContent = (data.connected_clients || []).length;
  document.getElementById("stat-ble").textContent = Object.keys(data.ble_devices).length;
  document.getElementById("meta").textContent =
    `Range: ${fmtTs(data.first_seen)} → ${fmtTs(data.last_seen)} · Updated ${new Date().toLocaleTimeString()}`;

  document.querySelector("#ap-table tbody").innerHTML = buildApRows(data.access_points);
  document.querySelector("#client-table tbody").innerHTML = buildClientRows(data.wifi_clients);
  document.querySelector("#conn-table tbody").innerHTML = buildConnRows(data.connected_clients || []);
  document.querySelector("#ble-table tbody").innerHTML = buildBleRows(data.ble_devices);

  ["ap-table", "client-table", "conn-table", "ble-table"].forEach(id => { reapplySort(id); applyFilter(id); });
}

function buildScanRows(results) {
  const entries = Object.entries(results);
  if (!entries.length) return emptyRow(3, "No scan results yet - waiting for a connected client with a known IP.");
  return entries.sort((a, b) => a[0].localeCompare(b[0])).map(([ip, info]) => {
    const ports = (info.ports && info.ports.length)
      ? info.ports.map(p => `${p.port}/${esc(p.service)}`).join(", ")
      : "(none open)";
    return `<tr><td>${esc(ip)}</td><td>${ports}</td><td>${esc(fmtTs(info.scanned_at))}</td></tr>`;
  }).join("");
}

async function pollScan() {
  const status = document.getElementById("scan-status");
  if (!SCAN_ENABLED) {
    status.textContent = "Disabled - restart this dashboard with --scan-ports to enable (only against devices you own/are authorized to test).";
    document.querySelector("#scan-table tbody").innerHTML = emptyRow(3, "Active scanning is disabled.");
    return;
  }
  try {
    const res = await fetch("/api/scan", { cache: "no-store" });
    const data = await res.json();
    const count = Object.keys(data.results || {}).length;
    status.textContent = count
      ? `Scanning ${count} device(s) with a known IP every ~20s.`
      : "Enabled - waiting for a connected client with a known IP to scan.";
    document.querySelector("#scan-table tbody").innerHTML = buildScanRows(data.results || {});
    reapplySort("scan-table");
    applyFilter("scan-table");
  } catch (e) {
    status.textContent = "Could not reach scan status.";
  }
}

async function poll() {
  const status = document.getElementById("status");
  try {
    const res = await fetch("/api/summary", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    render(await res.json());
    status.textContent = "Live";
    status.className = "ok";
  } catch (e) {
    status.textContent = "Disconnected - retrying...";
    status.className = "err";
  }
}

const MAX_FEED_LINES = 300;
let eventsSince = null; // seeded from the first /api/summary response - see render()

function timeOf(rec) {
  const raw = rec.timestamp;
  if (!raw) return "--:--:--";
  const d = new Date(raw);
  return isNaN(d) ? "--:--:--" : d.toLocaleTimeString([], { hour12: false });
}

function wifiLine(rec) {
  const ts = timeOf(rec);
  const ft = rec.frame_type || "?";
  if (ft === "beacon") {
    return `<span class="feed-ts">${ts}</span> <b>BEACON</b>     ssid=${esc(rec.ssid || "(hidden)")} bssid=${esc(rec.bssid)} ch=${esc(rec.channel ?? "?")} rssi=${esc(rec.rssi ?? "?")} enc=${esc(rec.encryption || "?")}`;
  }
  if (ft === "probe_req") {
    const name = rec.device_name ? ` name=${esc(rec.device_name)}` : "";
    return `<span class="feed-ts">${ts}</span> <b>PROBE_REQ</b>  client=${esc(rec.client_mac)}${name} ssid=${esc(rec.ssid || "(broadcast)")} rssi=${esc(rec.rssi ?? "?")}`;
  }
  if (ft === "probe_resp") {
    return `<span class="feed-ts">${ts}</span> <b>PROBE_RESP</b> bssid=${esc(rec.bssid)} client=${esc(rec.client_mac)} ssid=${esc(rec.ssid || "?")} rssi=${esc(rec.rssi ?? "?")}`;
  }
  const ip = rec.ip_address ? ` ip=${esc(rec.ip_address)}` : "";
  return `<span class="feed-ts">${ts}</span> <b>DATA</b>       bssid=${esc(rec.bssid)} client=${esc(rec.client_mac)}${ip} rssi=${esc(rec.rssi ?? "?")}`;
}

function bleLine(rec) {
  const ts = timeOf(rec);
  return `<span class="feed-ts">${ts}</span> <b>BLE</b> addr=${esc(rec.address)} name=${esc(rec.name || "?")} vendor=${esc(rec.vendor || "?")} rssi=${esc(rec.rssi ?? "?")}`;
}

let soundEnabled = true;
let audioCtx = null;
let lastBeepAt = 0;
const BEEP_FREQ = { beacon: 880, probe_req: 660, probe_resp: 740, data: 520, ble: 1300 };

function beep(kind) {
  if (!soundEnabled || !audioCtx || audioCtx.state !== "running") return;
  const now = performance.now();
  if (now - lastBeepAt < 120) return; // throttle so a burst of frames isn't a solid tone
  lastBeepAt = now;
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.type = "sine";
  osc.frequency.value = BEEP_FREQ[kind] || 600;
  gain.gain.setValueAtTime(0.16, audioCtx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.14);
  osc.connect(gain).connect(audioCtx.destination);
  osc.start();
  osc.stop(audioCtx.currentTime + 0.15);
}

const soundToggle = document.getElementById("sound-toggle");

function updateSoundLabel() {
  if (!soundEnabled) { soundToggle.textContent = "🔇 Sound: Off"; return; }
  if (audioCtx && audioCtx.state === "running") { soundToggle.textContent = "🔊 Sound: On"; return; }
  soundToggle.textContent = "🔈 Click to enable sound";
}
updateSoundLabel();

function ensureAudioCtx() {
  if (!audioCtx) {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
      return;
    }
  }
  if (audioCtx.state === "suspended") audioCtx.resume().then(updateSoundLabel);
  else updateSoundLabel();
}

// Browsers refuse to actually play audio until a real user gesture (click or
// keypress) happens, no matter what the code does - the label above is
// honest about this ("click to enable") instead of falsely claiming sound
// is already on. Any click/keydown anywhere unlocks it, not just the toggle.
soundToggle.addEventListener("click", (e) => {
  e.stopPropagation();
  if (soundEnabled && audioCtx && audioCtx.state === "running") {
    soundEnabled = false;
    updateSoundLabel();
  } else {
    soundEnabled = true;
    ensureAudioCtx();
  }
});

function unlockAudioOnAnyInteraction() {
  if (soundEnabled) ensureAudioCtx();
}
document.addEventListener("click", unlockAudioOnAnyInteraction);
document.addEventListener("keydown", unlockAudioOnAnyInteraction);

function appendFeedLine(panelId, html, cls) {
  const panel = document.getElementById(panelId);
  const empty = panel.querySelector(".feed-empty");
  if (empty) empty.remove();
  const atBottom = panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 20;
  const line = document.createElement("div");
  line.className = "feed-line " + cls;
  line.innerHTML = html;
  panel.appendChild(line);
  while (panel.children.length > MAX_FEED_LINES) panel.removeChild(panel.firstChild);
  if (atBottom) panel.scrollTop = panel.scrollHeight;
}

async function pollEvents() {
  if (eventsSince === null) return; // wait for the first /api/summary to seed the starting point
  try {
    const res = await fetch(`/api/events?since=${eventsSince}`, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    for (const rec of data.events) {
      if ("frame_type" in rec) {
        const ft = rec.frame_type || "data";
        appendFeedLine(ft === "data" ? "feed-conn" : "feed-wifi", wifiLine(rec), "ft-" + ft);
        beep(ft);
      } else if ("address" in rec) {
        appendFeedLine("feed-ble", bleLine(rec), "ft-ble");
        beep("ble");
      }
    }
    eventsSince = data.total;
  } catch (e) {
    // feed polling failures are non-fatal; the status badge from poll() covers connectivity
  }
}

poll();
pollEvents();
pollScan();
setInterval(poll, POLL_MS);
setInterval(pollEvents, 1000);
setInterval(pollScan, 5000);
</script>
</body>
</html>
"""
