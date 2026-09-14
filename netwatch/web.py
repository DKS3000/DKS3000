"""Flask web console: full monitoring dashboard for IP wake/sleep status and
MAC/BSSID connection records, with data filter options on every table.
"""

from flask import Flask, jsonify, render_template, request

from .ip_monitor import IpMonitor
from .store import CachedJsonlSource, filter_connections, filter_ip_events


def create_app(ip_monitor: IpMonitor, ip_event_source: CachedJsonlSource,
               rf_source: CachedJsonlSource) -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("dashboard.html")

    @app.get("/api/ip/status")
    def ip_status():
        rows = ip_monitor.snapshot()
        status = request.args.get("status") or None
        q = (request.args.get("q") or "").strip().lower()
        if status:
            rows = [r for r in rows if r["status"] == status]
        if q:
            rows = [r for r in rows if q in r["ip"].lower() or q in (r.get("hostname") or "").lower()]
        return jsonify(rows)

    @app.get("/api/ip/events")
    def ip_events():
        rows = filter_ip_events(
            ip_event_source.records(),
            ip=request.args.get("ip") or None,
            status=request.args.get("status") or None,
            since=request.args.get("since") or None,
            until=request.args.get("until") or None,
            limit=request.args.get("limit", type=int) or 200,
        )
        return jsonify(rows)

    @app.get("/api/connections")
    def connections():
        rows = filter_connections(
            rf_source.records(),
            q=request.args.get("q") or None,
            mac=request.args.get("mac") or None,
            bssid=request.args.get("bssid") or None,
            ssid=request.args.get("ssid") or None,
            vendor=request.args.get("vendor") or None,
            encryption=request.args.get("encryption") or None,
            kind=request.args.get("kind") or None,
            frame_type=request.args.get("frame_type") or None,
            since=request.args.get("since") or None,
            until=request.args.get("until") or None,
            limit=request.args.get("limit", type=int) or 200,
        )
        return jsonify(rows)

    @app.get("/api/summary")
    def summary():
        ip_rows = ip_monitor.snapshot()
        conn_rows = filter_connections(rf_source.records())
        macs = {r["mac"] for r in conn_rows if r.get("mac")}
        bssids = {r["bssid"] for r in conn_rows if r.get("bssid")}
        return jsonify({
            "ips_up": sum(1 for r in ip_rows if r["status"] == "up"),
            "ips_down": sum(1 for r in ip_rows if r["status"] == "down"),
            "ips_total": len(ip_rows),
            "unique_macs": len(macs),
            "unique_bssids": len(bssids),
            "total_connection_records": len(conn_rows),
        })

    return app
