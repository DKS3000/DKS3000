"""Local dashboard (binds 127.0.0.1). Test button is disabled while VPN is down."""
import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from . import report
from .tester import VPNNotConnected, run_test
from .vpn import VPN

DEFAULT_URL = "https://www.dgft.gov.in/"


def make_handler(vpn, history_path, url):
    class H(BaseHTTPRequestHandler):
        def _send(self, body, ctype="text/html", code=200, extra=None):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self):
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

        def _page(self):
            s = vpn.verify()
            e = html.escape
            led = "🟢 Connected" if s["connected"] else "🔴 Disconnected"
            opts = "".join("<option>%s</option>" % e(c) for c in vpn.countries())
            rows = "".join(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    e(str(r["timestamp"])), e(str(r["vpn_country"])), e(str(r["public_ip"])),
                    e(str(r["classification"])), e(str(r["response_time_ms"])))
                for r in reversed(report.load(history_path)))
            dis = "" if s["connected"] else " disabled"
            return ("<h1>DGFT access test</h1><p>VPN: %s | Provider: %s | Country/server: %s/%s | "
                    "Public IP: %s</p>"
                    "<form method=post action=/connect><select name=country>%s</select>"
                    "<button>Connect</button></form>"
                    "<form method=post action=/disconnect><button>Disconnect</button></form>"
                    "<form method=post action=/test><button%s>Run DGFT test</button></form>"
                    "<p><a href=/export.csv>CSV</a> <a href=/export.json>JSON</a></p>"
                    "<table border=1><tr><th>Time</th><th>Country</th><th>IP</th><th>Result</th>"
                    "<th>ms</th></tr>%s</table>") % (
                led, e(s["provider"]), e(str(s["country"])), e(str(s["server"])),
                e(str(s["public_ip"])), opts, dis, rows)

        def do_GET(self):
            if self.path == "/":
                self._send(self._page())
            elif self.path == "/export.json":
                self._send(json.dumps(report.load(history_path), indent=2), "application/json",
                           extra={"Content-Disposition": "attachment; filename=report.json"})
            elif self.path == "/export.csv":
                import io
                buf = io.StringIO()
                report.write_csv(buf, report.load(history_path))
                self._send(buf.getvalue(), "text/csv",
                           extra={"Content-Disposition": "attachment; filename=report.csv"})
            else:
                self._send("not found", code=404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            form = parse_qs(self.rfile.read(min(n, 4096)).decode())
            if self.path == "/connect":
                try:
                    vpn.connect(form.get("country", [""])[0])
                except Exception as exc:
                    return self._send("Connect failed: " + html.escape(str(exc)), code=400)
            elif self.path == "/disconnect":
                vpn.disconnect()
            elif self.path == "/test":
                try:
                    report.append(history_path, run_test(vpn, url))
                except VPNNotConnected:
                    return self._send("VPN disconnected; test disabled", code=409)
            return self._redirect()

        def log_message(self, *a):
            pass

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--history", default="dgft_history.jsonl")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    HTTPServer(("127.0.0.1", a.port), make_handler(VPN.from_file(a.config), a.history, a.url)).serve_forever()
