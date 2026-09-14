from mr_d_sniffer.logger import SessionLogger, export_csv, read_jsonl
from mr_d_sniffer.models import BleObservation, WifiObservation


def test_write_and_read_round_trip(tmp_path):
    logger = SessionLogger(str(tmp_path), "test")
    logger.write(WifiObservation(frame_type="beacon", bssid="AA:BB:CC:DD:EE:FF", ssid="TestNet"))
    logger.write(BleObservation(address="11:22:33:44:55:66", name="TestTag"))
    logger.close()

    records = list(read_jsonl(logger.path))
    assert len(records) == 2
    assert records[0]["frame_type"] == "beacon"
    assert records[0]["ssid"] == "TestNet"
    assert records[1]["address"] == "11:22:33:44:55:66"


def test_context_manager_closes_file(tmp_path):
    with SessionLogger(str(tmp_path), "ctx") as logger:
        logger.write(WifiObservation(frame_type="beacon", bssid="AA:BB:CC:DD:EE:FF"))
        path = logger.path
    # File handle closed; content is still readable and complete.
    records = list(read_jsonl(path))
    assert len(records) == 1


def test_export_csv(tmp_path):
    logger = SessionLogger(str(tmp_path), "csv")
    logger.write(WifiObservation(frame_type="beacon", bssid="AA:BB:CC:DD:EE:FF", ssid="Net1"))
    logger.write(BleObservation(address="11:22:33:44:55:66", name="Tag1"))
    logger.close()

    csv_path = str(tmp_path / "out.csv")
    export_csv(logger.path, csv_path)
    content = open(csv_path).read()
    assert "bssid" in content
    assert "address" in content
    assert "Net1" in content
    assert "Tag1" in content


def test_export_csv_empty_log_raises(tmp_path):
    empty_path = tmp_path / "empty.jsonl"
    empty_path.write_text("")
    try:
        export_csv(str(empty_path), str(tmp_path / "out.csv"))
        assert False, "expected ValueError"
    except ValueError:
        pass
