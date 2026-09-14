import json

import pytest

from netwatch.ip_monitor import IpMonitor
from netwatch.models import IpTarget
from netwatch.store import CachedJsonlSource
from netwatch.web import create_app


@pytest.fixture
def client(tmp_path):
    monitor = IpMonitor(
        [IpTarget(ip="10.0.0.1", hostname="router"), IpTarget(ip="10.0.0.2", hostname="nas")],
        ping_fn=lambda ip, timeout: 1.0 if ip == "10.0.0.1" else None,
    )
    monitor.poll_once()

    ip_events_path = tmp_path / "ip_events.jsonl"
    ip_events_path.write_text(
        json.dumps({"timestamp": "2026-01-01T00:00:00Z", "ip": "10.0.0.1",
                    "hostname": "router", "status": "up", "rtt_ms": 1.0}) + "\n"
    )

    rf_log_path = tmp_path / "combined.jsonl"
    rf_log_path.write_text(
        json.dumps({"timestamp": "2026-01-01T00:00:00Z", "frame_type": "beacon",
                    "bssid": "AA:BB:CC:DD:EE:FF", "ssid": "HomeNet", "vendor": "TP-Link"}) + "\n"
        + json.dumps({"timestamp": "2026-01-01T00:00:01Z", "address": "11:22:33:44:55:66",
                      "name": "Tag", "vendor": "Apple"}) + "\n"
    )

    app = create_app(monitor, CachedJsonlSource(paths=[str(ip_events_path)]),
                      CachedJsonlSource(paths=[str(rf_log_path)]))
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_serves_dashboard(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"netwatch" in res.data


def test_ip_status_filter_by_status(client):
    res = client.get("/api/ip/status?status=down")
    rows = res.get_json()
    assert len(rows) == 1
    assert rows[0]["ip"] == "10.0.0.2"


def test_ip_status_filter_by_query(client):
    res = client.get("/api/ip/status?q=router")
    rows = res.get_json()
    assert len(rows) == 1
    assert rows[0]["ip"] == "10.0.0.1"


def test_ip_events_endpoint(client):
    res = client.get("/api/ip/events")
    rows = res.get_json()
    assert len(rows) == 1
    assert rows[0]["status"] == "up"
    assert rows[0]["ip"] == "10.0.0.1"


def test_connections_filter_by_kind(client):
    res = client.get("/api/connections?kind=ble")
    rows = res.get_json()
    assert len(rows) == 1
    assert rows[0]["mac"] == "11:22:33:44:55:66"


def test_connections_search_query(client):
    res = client.get("/api/connections?q=homenet")
    rows = res.get_json()
    assert len(rows) == 1
    assert rows[0]["ssid"] == "HomeNet"


def test_summary_endpoint(client):
    res = client.get("/api/summary")
    body = res.get_json()
    assert body["ips_total"] == 2
    assert body["ips_up"] == 1
    assert body["ips_down"] == 1
    assert body["unique_macs"] == 2  # the beacon's bssid + the BLE address
    assert body["unique_bssids"] == 1
    assert body["total_connection_records"] == 2
