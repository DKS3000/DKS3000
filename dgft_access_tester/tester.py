"""Plain HTTP(S) access test. No auth, CAPTCHA, or WAF bypass; no credentials handled."""
import datetime
import http.client
import time
import urllib.parse

ALLOWED_HOSTS = {"dgft.gov.in", "www.dgft.gov.in"}
MAX_REDIRECTS = 5
SENSITIVE = {"set-cookie", "authorization"}


class VPNNotConnected(Exception):
    pass


def classify(status):
    if status is None:
        return "Timeout/Error"
    if status == 403:
        return "403 Forbidden"
    if status == 429:
        return "429 Rate limited"
    if 500 <= status < 600:
        return "5xx Server error"
    if 200 <= status < 300:
        return "200 OK" if status == 200 else "2xx Success"
    if 300 <= status < 400:
        return "3xx Redirect"
    return "%d Other" % status


def _check_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https") or (p.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("URL not an authorized DGFT target: %s" % url)
    return p


def _fetch(url, timeout):
    p = _check_url(url)
    cls = http.client.HTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
    conn = cls(p.hostname, p.port, timeout=timeout)
    try:
        path = p.path or "/"
        if p.query:
            path += "?" + p.query
        conn.request("GET", path, headers={"User-Agent": "dgft-access-tester/1.0 (authorized)"})
        r = conn.getresponse()
        r.read(0)
        return r.status, {k: v for k, v in r.getheaders() if k.lower() not in SENSITIVE}
    finally:
        conn.close()


def run_test(vpn, url, timeout=20, fetch=_fetch):
    """Verify VPN, then request url. Refuses to run if VPN is not verified."""
    _check_url(url)
    state = vpn.verify()
    if not state["connected"]:
        raise VPNNotConnected("VPN disconnected; test not run")
    rec = {"timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "vpn_provider": state["provider"], "vpn_country": state["country"],
           "vpn_server": state["server"], "public_ip": state["public_ip"],
           "url": url, "timeout_s": timeout, "status": None, "headers": {},
           "response_time_ms": None, "redirects": [], "error": None}
    current, start = url, time.monotonic()
    try:
        for _ in range(MAX_REDIRECTS + 1):
            status, headers = fetch(current, timeout)
            rec["status"], rec["headers"] = status, headers
            loc = headers.get("Location") or headers.get("location")
            if 300 <= status < 400 and loc:
                nxt = urllib.parse.urljoin(current, loc)
                rec["redirects"].append({"status": status, "to": nxt})
                try:
                    _check_url(nxt)
                except ValueError:
                    break  # never follow off the authorized host
                current = nxt
                continue
            break
    except Exception as e:  # timeout / network error
        rec["status"], rec["error"] = None, type(e).__name__
    rec["response_time_ms"] = round((time.monotonic() - start) * 1000, 1)
    rec["classification"] = classify(rec["status"])
    return rec
