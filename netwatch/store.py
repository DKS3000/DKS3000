"""Filtering + caching layer over JSONL logs (RF connection records and IP events)."""

import glob
import os
from typing import Dict, Iterable, List, Optional, Tuple

from rf_sniffer.logger import read_jsonl


class CachedJsonlSource:
    """Reads one or more JSONL files, re-reading a file only when it changes.

    Accepts explicit `paths` and/or a `glob_dir` (+ `glob_pattern`) to pick
    up every matching log in a directory, e.g. a whole `logs/` folder of
    rf_sniffer capture sessions.
    """

    def __init__(self, paths: Iterable[str] = (), glob_dir: Optional[str] = None,
                 glob_pattern: str = "*.jsonl"):
        self._paths = list(paths)
        self._glob_dir = glob_dir
        self._glob_pattern = glob_pattern
        self._cache: Dict[str, Tuple[Tuple[float, int], List[dict]]] = {}

    def _resolve_paths(self) -> List[str]:
        paths = list(self._paths)
        if self._glob_dir:
            paths.extend(sorted(glob.glob(os.path.join(self._glob_dir, self._glob_pattern))))
        seen = set()
        result = []
        for path in paths:
            if path not in seen and os.path.isfile(path):
                seen.add(path)
                result.append(path)
        return result

    def records(self) -> List[dict]:
        all_records: List[dict] = []
        for path in self._resolve_paths():
            stat = os.stat(path)
            key = (stat.st_mtime, stat.st_size)
            cached = self._cache.get(path)
            if cached is None or cached[0] != key:
                self._cache[path] = (key, list(read_jsonl(path)))
            all_records.extend(self._cache[path][1])
        return all_records


def _record_kind(rec: dict) -> str:
    if "frame_type" in rec:
        return "wifi"
    if "address" in rec:
        return "ble"
    return "unknown"


def normalize_connection(rec: dict) -> dict:
    """Flatten a raw rf_sniffer WiFi or BLE record into one common shape."""
    kind = _record_kind(rec)
    if kind == "wifi":
        mac = rec.get("client_mac") or rec.get("bssid")
    elif kind == "ble":
        mac = rec.get("address")
    else:
        mac = None
    return {
        "kind": kind,
        "timestamp": rec.get("timestamp"),
        "mac": mac,
        "bssid": rec.get("bssid"),
        "client_mac": rec.get("client_mac"),
        "ssid": rec.get("ssid") or rec.get("name"),
        "name": rec.get("name"),
        "frame_type": rec.get("frame_type"),
        "channel": rec.get("channel"),
        "rssi": rec.get("rssi"),
        "encryption": rec.get("encryption"),
        "vendor": rec.get("vendor"),
    }


def filter_connections(records: Iterable[dict], q: Optional[str] = None, mac: Optional[str] = None,
                        bssid: Optional[str] = None, ssid: Optional[str] = None,
                        vendor: Optional[str] = None, encryption: Optional[str] = None,
                        kind: Optional[str] = None, frame_type: Optional[str] = None,
                        since: Optional[str] = None, until: Optional[str] = None,
                        limit: Optional[int] = None) -> List[dict]:
    """Normalize + filter WiFi/BLE connection records. Filters are ANDed
    together; string filters match case-insensitive substrings. Results are
    sorted newest-first.
    """
    normalized = [normalize_connection(r) for r in records]

    def matches(rec: dict) -> bool:
        if kind and rec["kind"] != kind:
            return False
        if frame_type and rec.get("frame_type") != frame_type:
            return False
        if mac and mac.lower() not in (rec.get("mac") or "").lower():
            return False
        if bssid and bssid.lower() not in (rec.get("bssid") or "").lower():
            return False
        if ssid and ssid.lower() not in (rec.get("ssid") or "").lower():
            return False
        if vendor and vendor.lower() not in (rec.get("vendor") or "").lower():
            return False
        if encryption and encryption.lower() != (rec.get("encryption") or "").lower():
            return False
        ts = rec.get("timestamp") or ""
        if since and ts < since:
            return False
        if until and ts > until:
            return False
        if q:
            haystack = " ".join(str(v) for v in rec.values() if v is not None).lower()
            if q.lower() not in haystack:
                return False
        return True

    filtered = [r for r in normalized if matches(r)]
    filtered.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    if limit is not None:
        filtered = filtered[:limit]
    return filtered


def filter_ip_events(records: Iterable[dict], ip: Optional[str] = None, status: Optional[str] = None,
                      since: Optional[str] = None, until: Optional[str] = None,
                      limit: Optional[int] = None) -> List[dict]:
    """Filter IP wake/sleep transition events. Results are sorted newest-first."""

    def matches(rec: dict) -> bool:
        if ip and ip.lower() not in (rec.get("ip") or "").lower():
            return False
        if status and rec.get("status") != status:
            return False
        ts = rec.get("timestamp") or ""
        if since and ts < since:
            return False
        if until and ts > until:
            return False
        return True

    filtered = [r for r in records if matches(r)]
    filtered.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    if limit is not None:
        filtered = filtered[:limit]
    return filtered
