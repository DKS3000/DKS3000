from rf_sniffer.report import render_html, render_markdown, summarize


def test_summarize_wifi_and_ble():
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "frame_type": "beacon", "bssid": "AA:BB:CC:DD:EE:FF",
         "ssid": "HomeNet", "channel": 6, "rssi": -40, "encryption": "WPA2/WPA3", "vendor": "TP-Link"},
        {"timestamp": "2026-01-01T00:00:01Z", "frame_type": "beacon", "bssid": "AA:BB:CC:DD:EE:FF",
         "ssid": "HomeNet", "channel": 6, "rssi": -55, "encryption": "WPA2/WPA3", "vendor": "TP-Link"},
        {"timestamp": "2026-01-01T00:00:02Z", "frame_type": "probe_req", "client_mac": "11:22:33:44:55:66",
         "ssid": "HomeNet", "rssi": -60},
        {"timestamp": "2026-01-01T00:00:03Z", "address": "66:55:44:33:22:11", "name": "SensorTag",
         "rssi": -70, "vendor": "Apple"},
    ]

    summary = summarize(records)
    assert summary["total_records"] == 4
    assert summary["wifi_frame_count"] == 3
    assert summary["ble_frame_count"] == 1
    assert summary["first_seen"] == "2026-01-01T00:00:00Z"
    assert summary["last_seen"] == "2026-01-01T00:00:03Z"

    ap = summary["access_points"]["AA:BB:CC:DD:EE:FF"]
    assert ap["count"] == 2
    assert ap["best_rssi"] == -40  # strongest of -40/-55
    assert "HomeNet" in ap["ssids"]

    client = summary["wifi_clients"]["11:22:33:44:55:66"]
    assert client["count"] == 1
    assert "HomeNet" in client["ssids_probed"]

    dev = summary["ble_devices"]["66:55:44:33:22:11"]
    assert dev["name"] == "SensorTag"
    assert dev["vendor"] == "Apple"


def test_render_markdown_includes_sections():
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "frame_type": "beacon", "bssid": "AA:BB:CC:DD:EE:FF",
         "ssid": "HomeNet", "channel": 6, "rssi": -40, "encryption": "OPEN", "vendor": None},
        {"timestamp": "2026-01-01T00:00:01Z", "address": "66:55:44:33:22:11", "name": None,
         "rssi": -70, "vendor": None},
    ]
    summary = summarize(records)
    markdown = render_markdown(summary, "session.jsonl")
    assert "WiFi Access Points" in markdown
    assert "BLE Devices" in markdown
    assert "AA:BB:CC:DD:EE:FF" in markdown
    assert "66:55:44:33:22:11" in markdown


def test_summarize_empty():
    summary = summarize([])
    assert summary["total_records"] == 0
    assert summary["first_seen"] is None
    assert summary["access_points"] == {}


def test_render_html_includes_data_and_is_self_contained():
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "frame_type": "beacon", "bssid": "AA:BB:CC:DD:EE:FF",
         "ssid": "HomeNet", "channel": 6, "rssi": -40, "encryption": "WPA2/WPA3", "vendor": "TP-Link"},
        {"timestamp": "2026-01-01T00:00:01Z", "frame_type": "probe_req", "client_mac": "11:22:33:44:55:66",
         "ssid": "HomeNet", "rssi": -60},
        {"timestamp": "2026-01-01T00:00:02Z", "address": "66:55:44:33:22:11", "name": "SensorTag",
         "rssi": -70, "vendor": "Apple"},
    ]
    summary = summarize(records)
    html = render_html(summary, "session.jsonl")

    assert html.startswith("<!doctype html>")
    assert "<title>RF Recon Session Report</title>" in html
    assert "AA:BB:CC:DD:EE:FF" in html
    assert "HomeNet" in html
    assert "11:22:33:44:55:66" in html
    assert "SensorTag" in html
    assert "-40 dBm" in html
    # Self-contained: no external script/stylesheet references.
    assert "http://" not in html and "https://" not in html
    assert "<script src=" not in html
    assert '<link rel="stylesheet"' not in html


def test_render_html_escapes_untrusted_fields():
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "frame_type": "beacon", "bssid": "AA:BB:CC:DD:EE:FF",
         "ssid": "<script>alert(1)</script>", "channel": 6, "rssi": -40, "encryption": "OPEN", "vendor": None},
    ]
    summary = summarize(records)
    html = render_html(summary, "session.jsonl")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_html_empty_sections():
    summary = summarize([])
    html = render_html(summary, "session.jsonl")
    assert "No WiFi access points captured." in html
    assert "No probing WiFi clients captured." in html
    assert "No BLE devices captured." in html
