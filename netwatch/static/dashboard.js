const REFRESH_MS = 5000;

function qs(params) {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") usp.set(key, value);
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function localToIso(value) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString();
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

function renderRows(tableId, rows, rowFn, colspan) {
  const tbody = document.querySelector(`#${tableId} tbody`);
  tbody.innerHTML = rows.length
    ? rows.map(rowFn).join("")
    : `<tr><td colspan="${colspan}" class="empty">no records</td></tr>`;
}

async function refreshSummary() {
  try {
    const s = await fetchJson("/api/summary");
    document.getElementById("summary").textContent =
      `IPs: ${s.ips_up} up / ${s.ips_down} down (${s.ips_total} total)  ·  ` +
      `MACs seen: ${s.unique_macs}  ·  BSSIDs seen: ${s.unique_bssids}  ·  ` +
      `connection records: ${s.total_connection_records}`;
  } catch (e) {
    // keep last known summary on a transient fetch failure
  }
}

async function refreshIpStatus() {
  const params = {
    q: document.getElementById("ip-q").value,
    status: document.getElementById("ip-status").value,
  };
  const rows = await fetchJson(`/api/ip/status${qs(params)}`);
  renderRows("ip-status-table", rows, (r) => `
    <tr class="status-${escapeHtml(r.status)}">
      <td>${escapeHtml(r.ip)}</td>
      <td>${escapeHtml(r.hostname)}</td>
      <td><span class="badge badge-${escapeHtml(r.status)}">${escapeHtml(r.status)}</span></td>
      <td>${escapeHtml(r.since)}</td>
      <td>${escapeHtml(r.last_checked)}</td>
      <td>${r.rtt_ms ?? ""}</td>
    </tr>`, 6);
}

async function refreshIpEvents() {
  const params = {
    ip: document.getElementById("ev-ip").value,
    status: document.getElementById("ev-status").value,
    since: localToIso(document.getElementById("ev-since").value),
    until: localToIso(document.getElementById("ev-until").value),
  };
  const rows = await fetchJson(`/api/ip/events${qs(params)}`);
  renderRows("ip-events-table", rows, (r) => `
    <tr class="status-${escapeHtml(r.status)}">
      <td>${escapeHtml(r.timestamp)}</td>
      <td>${escapeHtml(r.ip)}</td>
      <td>${escapeHtml(r.hostname)}</td>
      <td><span class="badge badge-${escapeHtml(r.status)}">${r.status === "up" ? "wake" : "sleep"}</span></td>
      <td>${r.rtt_ms ?? ""}</td>
    </tr>`, 5);
}

async function refreshConnections() {
  const params = {
    q: document.getElementById("conn-q").value,
    kind: document.getElementById("conn-kind").value,
    mac: document.getElementById("conn-mac").value,
    bssid: document.getElementById("conn-bssid").value,
    ssid: document.getElementById("conn-ssid").value,
    vendor: document.getElementById("conn-vendor").value,
  };
  const rows = await fetchJson(`/api/connections${qs(params)}`);
  renderRows("connections-table", rows, (r) => `
    <tr>
      <td>${escapeHtml(r.timestamp)}</td>
      <td>${escapeHtml(r.kind)}</td>
      <td>${escapeHtml(r.frame_type)}</td>
      <td>${escapeHtml(r.mac)}</td>
      <td>${escapeHtml(r.bssid)}</td>
      <td>${escapeHtml(r.ssid)}</td>
      <td>${escapeHtml(r.vendor)}</td>
      <td>${escapeHtml(r.encryption)}</td>
      <td>${r.rssi ?? ""}</td>
    </tr>`, 9);
}

function refreshAll() {
  refreshSummary();
  refreshIpStatus();
  refreshIpEvents();
  refreshConnections();
}

document.querySelectorAll(".filters input, .filters select").forEach((el) => {
  el.addEventListener("input", refreshAll);
  el.addEventListener("change", refreshAll);
});

refreshAll();
setInterval(refreshAll, REFRESH_MS);
