import pytest

scapy = pytest.importorskip("scapy.all")

from scapy.layers.dot11 import Dot11, Dot11Beacon, Dot11Elt, Dot11ProbeReq, RadioTap

from mr_d_sniffer.wifi_sniffer import classify_encryption, extract_channel, extract_ssid, parse_packet


def _beacon(ssid="TestNet", channel=6, rsn=False, privacy=False, rssi=-42):
    cap = "privacy" if privacy or rsn else ""
    dot11 = Dot11(type=0, subtype=8, addr1="ff:ff:ff:ff:ff:ff",
                  addr2="AA:BB:CC:DD:EE:FF", addr3="AA:BB:CC:DD:EE:FF")
    beacon = Dot11Beacon(cap=cap)
    elt_ssid = Dot11Elt(ID=0, info=ssid.encode())
    elt_channel = Dot11Elt(ID=3, info=bytes([channel]))
    pkt = RadioTap(present="dBm_AntSignal", dBm_AntSignal=rssi) / dot11 / beacon / elt_ssid / elt_channel
    if rsn:
        # Minimal RSN element (ID 48); contents don't need to be fully valid
        # for our classifier, which only checks for its presence.
        elt_rsn = Dot11Elt(ID=48, info=b"\x01\x00\x00\x0f\xac\x04")
        pkt = pkt / elt_rsn
    return pkt


def test_extract_ssid():
    pkt = _beacon(ssid="HomeWifi")
    assert extract_ssid(pkt) == "HomeWifi"


def test_extract_channel():
    pkt = _beacon(channel=11)
    assert extract_channel(pkt) == 11


def test_classify_encryption_open():
    pkt = _beacon(rsn=False, privacy=False)
    assert classify_encryption(pkt) == "OPEN"


def test_classify_encryption_wpa2():
    pkt = _beacon(rsn=True)
    assert classify_encryption(pkt) == "WPA2/WPA3"


def test_parse_beacon_packet():
    pkt = _beacon(ssid="HomeWifi", channel=6, rsn=True, rssi=-55)
    obs = parse_packet(pkt)
    assert obs is not None
    assert obs.frame_type == "beacon"
    assert obs.bssid == "AA:BB:CC:DD:EE:FF"
    assert obs.ssid == "HomeWifi"
    assert obs.channel == 6
    assert obs.rssi == -55
    assert obs.encryption == "WPA2/WPA3"


def test_parse_probe_request():
    dot11 = Dot11(type=0, subtype=4, addr1="ff:ff:ff:ff:ff:ff",
                   addr2="11:22:33:44:55:66", addr3="ff:ff:ff:ff:ff:ff")
    elt_ssid = Dot11Elt(ID=0, info=b"SomeNetwork")
    pkt = RadioTap(present="dBm_AntSignal", dBm_AntSignal=-60) / dot11 / Dot11ProbeReq() / elt_ssid
    obs = parse_packet(pkt)
    assert obs is not None
    assert obs.frame_type == "probe_req"
    assert obs.client_mac == "11:22:33:44:55:66"
    assert obs.ssid == "SomeNetwork"
    assert obs.rssi == -60
