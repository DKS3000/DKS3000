from types import SimpleNamespace

from rf_sniffer.ble_sniffer import parse_advertisement


def _device(address="66:55:44:33:22:11", name=None):
    return SimpleNamespace(address=address, name=name)


def _adv(local_name=None, rssi=-70, tx_power=None, manufacturer_data=None, service_uuids=None):
    return SimpleNamespace(
        local_name=local_name,
        rssi=rssi,
        tx_power=tx_power,
        manufacturer_data=manufacturer_data or {},
        service_uuids=service_uuids or [],
    )


def test_parse_basic_advertisement():
    obs = parse_advertisement(_device(name="FallbackName"), _adv(local_name=None, rssi=-65))
    assert obs.address == "66:55:44:33:22:11"
    assert obs.name == "FallbackName"
    assert obs.rssi == -65


def test_local_name_preferred_over_device_name():
    obs = parse_advertisement(_device(name="Old"), _adv(local_name="New"))
    assert obs.name == "New"


def test_vendor_lookup_from_manufacturer_data():
    obs = parse_advertisement(_device(), _adv(manufacturer_data={0x004C: b"\x02\x15"}))
    assert obs.vendor == "Apple"
    assert obs.manufacturer_ids == [0x004C]


def test_unknown_vendor_is_none():
    obs = parse_advertisement(_device(), _adv(manufacturer_data={0x9999: b"\x00"}))
    assert obs.vendor is None


def test_service_uuids_captured():
    obs = parse_advertisement(_device(), _adv(service_uuids=["0000180d-0000-1000-8000-00805f9b34fb"]))
    assert obs.service_uuids == ["0000180d-0000-1000-8000-00805f9b34fb"]
