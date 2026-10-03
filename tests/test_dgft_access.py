import pytest

from dgft_access_tester import report
from dgft_access_tester.tester import VPNNotConnected, run_test
from dgft_access_tester.vpn import VPN


def make_vpn(ips, status_ok=True):
    it = iter(ips)
    v = VPN({"provider": "P", "status_cmd": ["true" if status_ok else "false"],
             "servers": {"DE": {"server": "de1", "connect_cmd": ["true"]}}},
            ip_func=lambda: next(it))
    return v


def test_refuses_when_disconnected():
    v = make_vpn(["1.1.1.1"] * 3)
    with pytest.raises(VPNNotConnected):
        run_test(v, "https://www.dgft.gov.in/", fetch=lambda u, t: (200, {}))


def test_same_ip_is_not_connected():
    v = make_vpn(["1.1.1.1"] * 3)
    v.connect("DE")
    assert not v.verify()["connected"]


def test_403_recorded_with_redirect():
    v = make_vpn(["1.1.1.1", "2.2.2.2", "2.2.2.2"])
    v.connect("DE")
    calls = [(302, {"Location": "/x"}), (403, {"Server": "s"})]
    rec = run_test(v, "https://www.dgft.gov.in/", fetch=lambda u, t: calls.pop(0))
    assert rec["status"] == 403 and rec["classification"] == "403 Forbidden"
    assert len(rec["redirects"]) == 1 and rec["vpn_country"] == "DE"


def test_rejects_other_hosts():
    v = make_vpn(["1.1.1.1"] * 3)
    with pytest.raises(ValueError):
        run_test(v, "https://example.com/", fetch=lambda u, t: (200, {}))


def test_csv_formula_escape(tmp_path):
    p = tmp_path / "r.csv"
    report.to_csv([{"timestamp": "t", "error": "=cmd", "redirects": [], "headers": {}}], str(p))
    assert "'=cmd" in p.read_text()
