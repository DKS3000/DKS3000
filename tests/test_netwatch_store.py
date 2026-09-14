import json

from netwatch.store import CachedJsonlSource, filter_connections, filter_ip_events

WIFI_RECORDS = [
    {"timestamp": "2026-01-01T00:00:00Z", "frame_type": "beacon", "bssid": "AA:BB:CC:DD:EE:01",
     "ssid": "HomeNet", "channel": 6, "rssi": -40, "encryption": "WPA2/WPA3", "vendor": "TP-Link"},
    {"timestamp": "2026-01-01T00:00:05Z", "frame_type": "probe_req", "client_mac": "11:22:33:44:55:66",
     "ssid": "HomeNet", "rssi": -60, "vendor": "Apple"},
]
BLE_RECORDS = [
    {"timestamp": "2026-01-01T00:00:03Z", "address": "66:55:44:33:22:11", "name": "SensorTag",
     "rssi": -70, "vendor": "Apple"},
]

IP_EVENTS = [
    {"timestamp": "2026-01-01T00:00:00Z", "ip": "10.0.0.1", "hostname": "router", "status": "up"},
    {"timestamp": "2026-01-01T00:05:00Z", "ip": "10.0.0.1", "hostname": "router", "status": "down"},
    {"timestamp": "2026-01-01T00:06:00Z", "ip": "10.0.0.2", "hostname": "nas", "status": "up"},
]


def test_filter_connections_by_kind():
    rows = filter_connections(WIFI_RECORDS + BLE_RECORDS, kind="ble")
    assert len(rows) == 1
    assert rows[0]["mac"] == "66:55:44:33:22:11"


def test_filter_connections_by_mac_substring():
    rows = filter_connections(WIFI_RECORDS + BLE_RECORDS, mac="11:22:33")
    assert len(rows) == 1
    assert rows[0]["mac"] == "11:22:33:44:55:66"


def test_filter_connections_by_query_across_fields():
    rows = filter_connections(WIFI_RECORDS + BLE_RECORDS, q="sensortag")
    assert len(rows) == 1
    assert rows[0]["name"] == "SensorTag"


def test_filter_connections_sorted_desc_and_limited():
    rows = filter_connections(WIFI_RECORDS + BLE_RECORDS, limit=1)
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-01-01T00:00:05Z"


def test_filter_connections_time_range():
    rows = filter_connections(WIFI_RECORDS + BLE_RECORDS, since="2026-01-01T00:00:04Z")
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2026-01-01T00:00:05Z"


def test_filter_connections_by_encryption_exact_match():
    rows = filter_connections(WIFI_RECORDS, encryption="wpa2/wpa3")
    assert len(rows) == 1
    assert rows[0]["bssid"] == "AA:BB:CC:DD:EE:01"


def test_filter_ip_events_by_status():
    rows = filter_ip_events(IP_EVENTS, status="down")
    assert len(rows) == 1
    assert rows[0]["ip"] == "10.0.0.1"


def test_filter_ip_events_by_ip():
    rows = filter_ip_events(IP_EVENTS, ip="10.0.0.2")
    assert len(rows) == 1
    assert rows[0]["hostname"] == "nas"


def test_filter_ip_events_sorted_desc():
    rows = filter_ip_events(IP_EVENTS)
    assert [r["timestamp"] for r in rows] == [
        "2026-01-01T00:06:00Z", "2026-01-01T00:05:00Z", "2026-01-01T00:00:00Z",
    ]


def test_cached_jsonl_source_reloads_when_file_changes(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_text(json.dumps({"ip": "10.0.0.1", "status": "up", "timestamp": "t1"}) + "\n")
    source = CachedJsonlSource(paths=[str(path)])
    assert len(source.records()) == 1

    path.write_text(
        json.dumps({"ip": "10.0.0.1", "status": "up", "timestamp": "t1"}) + "\n"
        + json.dumps({"ip": "10.0.0.1", "status": "down", "timestamp": "t2"}) + "\n"
    )
    assert len(source.records()) == 2


def test_cached_jsonl_source_glob_dir(tmp_path):
    (tmp_path / "wifi_1.jsonl").write_text(json.dumps({"frame_type": "beacon", "bssid": "AA"}) + "\n")
    (tmp_path / "ble_1.jsonl").write_text(json.dumps({"address": "BB"}) + "\n")
    (tmp_path / "notes.txt").write_text("ignore me")

    source = CachedJsonlSource(glob_dir=str(tmp_path))
    records = source.records()
    assert len(records) == 2


def test_cached_jsonl_source_missing_dir_returns_empty(tmp_path):
    source = CachedJsonlSource(glob_dir=str(tmp_path / "does-not-exist"))
    assert source.records() == []
