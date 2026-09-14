from rf_sniffer.oui import lookup_ble_company, lookup_mac_vendor


def test_known_mac_prefix():
    assert lookup_mac_vendor("DC:A6:32:11:22:33") == "Raspberry Pi Foundation"


def test_mac_case_and_dash_insensitive():
    assert lookup_mac_vendor("dc-a6-32-11-22-33") == "Raspberry Pi Foundation"


def test_unknown_mac_returns_none():
    assert lookup_mac_vendor("FF:FF:FF:00:00:00") is None


def test_short_or_empty_mac_returns_none():
    assert lookup_mac_vendor("") is None
    assert lookup_mac_vendor("DC:A6") is None


def test_known_ble_company():
    assert lookup_ble_company(0x004C) == "Apple"


def test_unknown_ble_company_returns_none():
    assert lookup_ble_company(0xFFFF) is None
