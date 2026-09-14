import json
import urllib.error
import urllib.request

from rf_sniffer.live_server import start_live_server


def _get(url: str) -> str:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.read().decode("utf-8")


def test_live_server_serves_and_reflects_growing_log(tmp_path):
    log_path = tmp_path / "session.jsonl"
    log_path.write_text("")  # capture hasn't logged anything yet

    server = start_live_server(str(log_path), host="127.0.0.1", port=0, refresh_seconds=2)
    try:
        port = server.server_address[1]
        base = f"http://127.0.0.1:{port}/"

        html = _get(base)
        assert "<!doctype html>" in html
        assert "No WiFi access points captured." in html
        # Auto-refresh script present with the configured interval.
        assert "setTimeout(() => location.reload(), 2000)" in html

        # Simulate a capture appending a new observation while the
        # server is running - the next request should reflect it.
        record = {
            "timestamp": "2026-01-01T00:00:00Z", "frame_type": "beacon",
            "bssid": "AA:BB:CC:DD:EE:FF", "ssid": "LiveNet", "channel": 6,
            "rssi": -42, "encryption": "OPEN", "vendor": None,
        }
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

        html2 = _get(base)
        assert "LiveNet" in html2
        assert "AA:BB:CC:DD:EE:FF" in html2
    finally:
        server.shutdown()


def test_live_server_404_for_unknown_path(tmp_path):
    log_path = tmp_path / "session.jsonl"
    log_path.write_text("")

    server = start_live_server(str(log_path), host="127.0.0.1", port=0, refresh_seconds=5)
    try:
        port = server.server_address[1]
        try:
            _get(f"http://127.0.0.1:{port}/nope")
            assert False, "expected HTTPError"
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.shutdown()


def test_live_server_handles_missing_log_file(tmp_path):
    log_path = tmp_path / "does_not_exist.jsonl"

    server = start_live_server(str(log_path), host="127.0.0.1", port=0, refresh_seconds=5)
    try:
        port = server.server_address[1]
        html = _get(f"http://127.0.0.1:{port}/")
        assert "<!doctype html>" in html
        assert "No WiFi access points captured." in html
    finally:
        server.shutdown()
