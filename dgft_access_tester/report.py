import csv
import json
import os

FIELDS = ["timestamp", "vpn_provider", "vpn_country", "vpn_server", "public_ip", "url",
          "status", "classification", "response_time_ms", "redirects", "headers", "error"]


def append(path, rec):
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def _cell(v):
    if isinstance(v, str) and v[:1] in "=+-@\t\r":
        return "'" + v  # avoid CSV formula injection
    return v


def write_csv(f, records):
    w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
    w.writeheader()
    for r in records:
        row = {k: r.get(k) for k in FIELDS}
        row["redirects"] = json.dumps(row["redirects"])
        row["headers"] = json.dumps(row["headers"])
        w.writerow({k: _cell(v) for k, v in row.items()})


def to_csv(records, path):
    with open(path, "w", newline="") as f:
        write_csv(f, records)


def to_json(records, path):
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
