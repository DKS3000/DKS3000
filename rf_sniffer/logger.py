"""Structured session logging: append-only JSONL, with CSV export."""

import csv
import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Iterator


class SessionLogger:
    """Appends observation records to a JSONL file as they arrive.

    JSONL (one JSON object per line) is used instead of a single JSON
    array so a capture session survives being interrupted (Ctrl-C, power
    loss) without corrupting already-written records. Writes are
    lock-protected so WiFi (thread) and BLE (asyncio) capture can safely
    share one logger in "both" mode.
    """

    def __init__(self, out_dir: str, prefix: str):
        os.makedirs(out_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = os.path.join(out_dir, f"{prefix}_{stamp}.jsonl")
        self._fh = open(self.path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, record) -> None:
        data = asdict(record) if is_dataclass(record) else dict(record)
        line = json.dumps(data, default=str) + "\n"
        with self._lock:
            self._fh.write(line)
            self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def read_jsonl(path: str) -> Iterator[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def export_csv(jsonl_path: str, csv_path: str) -> str:
    """Flatten a JSONL log into a CSV. Column set is the union of all keys."""
    records = list(read_jsonl(jsonl_path))
    if not records:
        raise ValueError(f"No records found in {jsonl_path}")

    fieldnames: list[str] = []
    seen = set()
    for rec in records:
        for key in rec:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)
    return csv_path
