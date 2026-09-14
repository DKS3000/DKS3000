"""A tiny local HTTP server that serves the dashboard live while a
capture is running (or against any session log that's still growing),
so you can watch it update in a browser from another device on your
network instead of waiting for the capture to finish.

Stdlib only (http.server) - no extra dependencies beyond what `report`
already needs.
"""

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .logger import read_jsonl
from .report import render_html, summarize

_REFRESH_SCRIPT = """
<script>
  // Live mode: reload on an interval so the tables/cards reflect new
  // observations as they're captured. A full reload is simple and
  // robust; it does mean sort/filter state resets each refresh.
  setTimeout(() => location.reload(), {interval_ms});
</script>
"""


def _lan_ip() -> str:
    """Best-effort outbound-interface IP for printing a browsable URL.

    Uses a UDP "connect" (no packets are actually sent for UDP) purely
    to ask the OS which local interface would be used; falls back to
    localhost if there's no route (e.g. no network at all).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _make_handler(jsonl_path: str, refresh_seconds: float):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (BaseHTTPRequestHandler API)
            if self.path not in ("/", "/index.html"):
                self.send_response(404)
                self.end_headers()
                return
            try:
                records = list(read_jsonl(jsonl_path))
            except FileNotFoundError:
                records = []
            summary = summarize(records)
            html = render_html(summary, jsonl_path)
            html = html.replace(
                "</body>",
                _REFRESH_SCRIPT.format(interval_ms=int(refresh_seconds * 1000)) + "</body>",
            )
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002 - stdlib signature
            pass  # quiet; the CLI already prints capture progress

    return DashboardHandler


def start_live_server(jsonl_path: str, host: str = "0.0.0.0", port: int = 8000,
                       refresh_seconds: float = 5.0) -> ThreadingHTTPServer:
    """Start serving a self-refreshing dashboard for `jsonl_path` in a
    background thread. Returns the server so the caller can `.shutdown()`
    it when capture ends. Prints the URL(s) to visit."""
    handler = _make_handler(jsonl_path, refresh_seconds)
    server = ThreadingHTTPServer((host, port), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    lan_ip = _lan_ip()
    print(f"[live] dashboard serving at http://{lan_ip}:{server.server_address[1]}/ "
          f"(refreshing every {refresh_seconds:.0f}s)")
    print(f"[live] also reachable at http://localhost:{server.server_address[1]}/ on this machine")
    return server
