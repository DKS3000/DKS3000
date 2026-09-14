from rf_sniffer.oui import is_randomized_mac, lookup_ble_company, lookup_mac_vendor


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


def test_vendor_assigned_mac_is_not_randomized():
    # Real Raspberry Pi Foundation OUI: first octet 0xDC = 1101_1100, bit 0x02 clear.
    assert is_randomized_mac("DC:A6:32:11:22:33") is False


def test_locally_administered_mac_is_randomized():
    # 0x02 has the locally-administered bit set - the canonical "randomized" example.
    assert is_randomized_mac("02:11:22:33:44:55") is True
    # Real-world randomized addresses commonly look like this (e.g. iOS/Android).
    assert is_randomized_mac("BE:12:34:56:78:9A") is True


def test_randomized_mac_case_and_dash_insensitive():
    assert is_randomized_mac("02-11-22-33-44-55") is True
    assert is_randomized_mac("dc-a6-32-11-22-33") is False


def test_short_or_empty_mac_randomized_check_returns_none():
    assert is_randomized_mac("") is None
    assert is_randomized_mac(None) is None
