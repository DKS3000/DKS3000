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

from .report import _html_escape, summarize


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
    }


def _make_handler(jsonl_path: str, interval: float):
    html_body = _LIVE_HTML_TEMPLATE.replace(
        "__INTERVAL_MS__", str(int(interval * 1000))
    ).replace(
        "__SOURCE__", _html_escape(os.path.basename(jsonl_path))
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
            new_records = records[since:] if since < len(records) else []
            payload = json.dumps({"events": new_records, "total": len(records)}).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", payload)

        def _send(self, status: int, content_type: str, body: bytes):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def run_live_server(jsonl_path: str, port: int, interval: float = 2.0, open_browser: bool = False) -> None:
    handler = _make_handler(jsonl_path, interval)
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


_LIVE_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RF Recon - Live</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 1100px; margin: 0 auto; padding: 24px 16px; line-height: 1.5; }
  h1 { margin-bottom: 4px; display: flex; align-items: center; gap: 10px; }
  .muted { opacity: .65; font-size: .9em; }
  #status { font-size: .7em; padding: 3px 9px; border-radius: 999px; font-weight: 600; }
  #status.ok { background: rgba(47,158,68,.18); color: #2f9e44; }
  #status.err { background: rgba(224,49,49,.18); color: #e03131; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }
  .card { border: 1px solid currentColor; border-radius: 10px; padding: 14px; opacity: .95; }
  .card .n { font-size: 1.6em; font-weight: 700; display: block; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 28px; }
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

  .feed-wrap { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  @media (max-width: 700px) { .feed-wrap { grid-template-columns: 1fr; } }
  .feed-panel {
    background: #0d1117; border-radius: 10px; padding: 10px 12px;
    height: 320px; overflow-y: auto; font-family: "SF Mono", Consolas, "Courier New", monospace;
    font-size: 12.5px; line-height: 1.55;
  }
  .feed-panel h3 { margin: 0 0 8px; font-family: -apple-system, sans-serif; font-size: 13px;
                    color: #8b949e; text-transform: uppercase; letter-spacing: .04em; }
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
<h1>RF Recon - Live <span id="status" class="ok">Connecting...</span></h1>
<p class="muted">Source: __SOURCE__ &middot; <span id="meta">waiting for first update...</span></p>

<section class="grid">
  <div class="card"><span class="n" id="stat-total">0</span>Total records</div>
  <div class="card"><span class="n" id="stat-ap">0</span>Access points</div>
  <div class="card"><span class="n" id="stat-client">0</span>Probing clients</div>
  <div class="card"><span class="n" id="stat-ble">0</span>BLE devices</div>
</section>

<section>
<h2>Live Event Feed</h2>
<div class="feed-wrap">
  <div class="feed-panel" id="feed-wifi"><div class="feed-empty">Waiting for WiFi frames...</div></div>
  <div class="feed-panel" id="feed-ble"><div class="feed-empty">Waiting for BLE advertisements...</div></div>
</div>
</section>

<section>
<h2>WiFi Access Points</h2>
<input type="search" data-filter-for="ap-table" placeholder="Filter by BSSID, SSID, vendor...">
<table id="ap-table">
<thead><tr>
<th data-numeric="0">BSSID</th><th data-numeric="0">SSID(s)</th><th data-numeric="0">Channel(s)</th>
<th data-numeric="0">Encryption</th><th data-numeric="0">Vendor</th><th data-numeric="1">Best RSSI</th><th data-numeric="1">Frames</th>
</tr></thead>
<tbody></tbody>
</table>
</section>

<section>
<h2>WiFi Probing Clients</h2>
<input type="search" data-filter-for="client-table" placeholder="Filter by MAC or SSID...">
<table id="client-table">
<thead><tr><th data-numeric="0">Client MAC</th><th data-numeric="0">SSIDs Probed</th><th data-numeric="1">Best RSSI</th><th data-numeric="1">Frames</th></tr></thead>
<tbody></tbody>
</table>
</section>

<section>
<h2>BLE Devices</h2>
<input type="search" data-filter-for="ble-table" placeholder="Filter by address, name, vendor...">
<table id="ble-table">
<thead><tr><th data-numeric="0">Address</th><th data-numeric="0">Name</th><th data-numeric="0">Vendor</th><th data-numeric="1">Best RSSI</th><th data-numeric="1">Advertisements</th></tr></thead>
<tbody></tbody>
</table>
</section>

<script>
const POLL_MS = __INTERVAL_MS__;
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

function buildApRows(aps) {
  const entries = Object.entries(aps).sort((a, b) => b[1].count - a[1].count);
  if (!entries.length) return emptyRow(7, "No WiFi access points captured yet.");
  return entries.map(([bssid, info]) => {
    const ssids = (info.ssids && info.ssids.length) ? info.ssids.join(", ") : "(hidden)";
    const channels = (info.channels || []).join(", ");
    const enc = (info.encryption && info.encryption.length) ? info.encryption.join(", ") : "?";
    return `<tr><td>${esc(bssid)}</td><td>${esc(ssids)}</td><td>${esc(channels)}</td>` +
           `<td>${esc(enc)}</td><td>${esc(info.vendor || "?")}</td>` +
           `<td>${sigCell(info.best_rssi)}</td><td>${info.count}</td></tr>`;
  }).join("");
}

function buildClientRows(clients) {
  const entries = Object.entries(clients).sort((a, b) => b[1].count - a[1].count);
  if (!entries.length) return emptyRow(4, "No probing WiFi clients captured yet.");
  return entries.map(([mac, info]) => {
    const ssids = (info.ssids_probed && info.ssids_probed.length) ? info.ssids_probed.join(", ") : "(broadcast)";
    return `<tr><td>${esc(mac)}</td><td>${esc(ssids)}</td><td>${sigCell(info.best_rssi)}</td><td>${info.count}</td></tr>`;
  }).join("");
}

function buildBleRows(devices) {
  const entries = Object.entries(devices).sort((a, b) => b[1].count - a[1].count);
  if (!entries.length) return emptyRow(5, "No BLE devices captured yet.");
  return entries.map(([addr, info]) => {
    return `<tr><td>${esc(addr)}</td><td>${esc(info.name || "?")}</td><td>${esc(info.vendor || "?")}</td>` +
           `<td>${sigCell(info.best_rssi)}</td><td>${info.count}</td></tr>`;
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
  document.getElementById("stat-total").textContent = data.total_records;
  document.getElementById("stat-ap").textContent = Object.keys(data.access_points).length;
  document.getElementById("stat-client").textContent = Object.keys(data.wifi_clients).length;
  document.getElementById("stat-ble").textContent = Object.keys(data.ble_devices).length;
  document.getElementById("meta").textContent =
    `Range: ${data.first_seen || "n/a"} → ${data.last_seen || "n/a"} · Updated ${new Date().toLocaleTimeString()}`;

  document.querySelector("#ap-table tbody").innerHTML = buildApRows(data.access_points);
  document.querySelector("#client-table tbody").innerHTML = buildClientRows(data.wifi_clients);
  document.querySelector("#ble-table tbody").innerHTML = buildBleRows(data.ble_devices);

  ["ap-table", "client-table", "ble-table"].forEach(id => { reapplySort(id); applyFilter(id); });
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
let eventsSince = 0;

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
    return `<span class="feed-ts">${ts}</span> <b>PROBE_REQ</b>  client=${esc(rec.client_mac)} ssid=${esc(rec.ssid || "(broadcast)")} rssi=${esc(rec.rssi ?? "?")}`;
  }
  if (ft === "probe_resp") {
    return `<span class="feed-ts">${ts}</span> <b>PROBE_RESP</b> bssid=${esc(rec.bssid)} client=${esc(rec.client_mac)} ssid=${esc(rec.ssid || "?")} rssi=${esc(rec.rssi ?? "?")}`;
  }
  return `<span class="feed-ts">${ts}</span> <b>DATA</b>       bssid=${esc(rec.bssid)} client=${esc(rec.client_mac)} rssi=${esc(rec.rssi ?? "?")}`;
}

function bleLine(rec) {
  const ts = timeOf(rec);
  return `<span class="feed-ts">${ts}</span> <b>BLE</b> addr=${esc(rec.address)} name=${esc(rec.name || "?")} vendor=${esc(rec.vendor || "?")} rssi=${esc(rec.rssi ?? "?")}`;
}

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
  try {
    const res = await fetch(`/api/events?since=${eventsSince}`, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    for (const rec of data.events) {
      if ("frame_type" in rec) {
        appendFeedLine("feed-wifi", wifiLine(rec), "ft-" + (rec.frame_type || "data"));
      } else if ("address" in rec) {
        appendFeedLine("feed-ble", bleLine(rec), "ft-ble");
      }
    }
    eventsSince = data.total;
  } catch (e) {
    // feed polling failures are non-fatal; the status badge from poll() covers connectivity
  }
}

poll();
pollEvents();
setInterval(poll, POLL_MS);
setInterval(pollEvents, 1000);
</script>
</body>
</html>
"""
