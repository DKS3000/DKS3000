# Instagram Profile Analyzer

Gathers everything you've uploaded to your own Instagram account and turns
it into one organized profile report: posting patterns, top hashtags and
keywords, follower/following overlap, and how much you comment/like on
others' content.

Two ways to feed it data:

1. **Official data export (recommended, no API setup needed).**
   Instagram → Settings → Accounts Center → *Your information and
   permissions* → *Download your information* → format **JSON**. Extract
   the ZIP you receive somewhere local, then run:

   ```bash
   pip install -r requirements.txt   # stdlib only for this mode; see below
   python -m instagram_analyzer analyze --export /path/to/extracted-export --out reports/
   ```

2. **Instagram Graph API (live data, for a Business/Creator account).**
   Requires linking a Facebook Page and creating a Meta developer app —
   see the setup steps at the top of `instagram_analyzer/graph_api.py`.
   Once you have a token and business account ID:

   ```bash
   pip install requests
   export IG_ACCESS_TOKEN=...
   export IG_BUSINESS_ACCOUNT_ID=...
   python -m instagram_analyzer fetch --out reports/
   ```

Both modes write the same two reports to the output directory:

- `profile_report.md` — organized Markdown summary
- `profile_report.html` — a self-contained, offline HTML dashboard

Add `--json path.json` to either command to also dump the full analysis as
raw JSON (useful if you want to feed it into something else).

## What gets analyzed

- Profile basics: name, bio, private/public, follower/following counts
- Posting cadence: totals, active date range, busiest weekday/hour,
  posts-per-month breakdown
- Content: top hashtags, top mentions, top caption keywords, average
  caption length
- Top performing posts by likes + comments (Graph API mode only, since the
  data export doesn't include engagement counts)
- Your own activity: comments and likes you've given, and who you interact
  with most
- Network insights: accounts you follow that don't follow back, and vice
  versa

## Why not scrape Instagram directly?

Automated scraping of Instagram (logging in with a bot, crawling pages)
violates Instagram's Terms of Service and can get your account flagged or
banned. Both modes here use data Instagram gives you directly and
officially: your own requested data export, or the official Graph API for
an account you own.

## Development

```bash
pip install -r requirements.txt
pytest
```

`tests/fixtures/sample_export/` contains a small hand-built export used by
the test suite, in the same folder layout Instagram produces.

---

# RF Recon Sniffer (WiFi + BLE)

A passive WiFi (802.11) and Bluetooth Low Energy reconnaissance tool for
a Raspberry Pi (or any Linux box), with detailed structured logging.
Built for **authorized security research** — pentest engagements, CTFs,
and auditing your own networks/devices. It does not attack, associate
with, or transmit anything at APs/devices; it only listens.

**Only run this against networks and devices you own, or where you have
explicit written authorization to test.** Passively capturing WiFi
management frames and BLE advertisements from third parties without
consent is illegal in many jurisdictions and against the Terms of
Service of most networks.

## What it captures

- **WiFi** (needs a monitor-mode-capable adapter): beacon frames (SSID,
  BSSID, channel, encryption type, RSSI), probe requests (which nearby
  clients are looking for which SSIDs), probe responses, and data-frame
  associations between clients and access points.
- **BLE**: every advertisement seen — device address, name, RSSI,
  manufacturer ID/vendor, TX power, and advertised service UUIDs.

Every observation is timestamped and vendor-tagged (best-effort OUI /
BLE company-ID lookup) and appended to a JSONL log as it's captured, so
a session survives being interrupted.

## Setup

```bash
pip install -r requirements.txt   # installs scapy + bleak
```

WiFi capture needs an interface already in monitor mode:

```bash
sudo ip link set wlan1 down
sudo iw dev wlan1 set type monitor
sudo ip link set wlan1 up
```

(A built-in Pi WiFi chip usually can't do monitor mode — use a USB
adapter with a monitor-mode-capable chipset, e.g. one based on
Atheros AR9271 or RTL8812AU.)

BLE capture uses the Pi's onboard Bluetooth via BlueZ — no extra setup
beyond `bleak` being installed, though you may need to run as root or
grant the interpreter capabilities depending on your BlueZ policy.

## Usage

```bash
# WiFi only, hopping channels 1-11, for 5 minutes
sudo python -m rf_sniffer wifi --iface wlan1mon --duration 300 --out logs/

# BLE only, until Ctrl-C
python -m rf_sniffer ble --out logs/

# Both at once, one combined log
sudo python -m rf_sniffer both --iface wlan1mon --duration 300 --out logs/

# Turn a captured session into a readable report
python -m rf_sniffer report --log logs/combined_20260101T000000Z.jsonl \
    --out reports/session.md --csv reports/session.csv
```

Add `--report path/to/out.md` to `wifi`/`ble`/`both` to generate the
markdown report automatically when the capture finishes.

## Extending range

"Long range" here is a hardware property, not something software adds
on its own — this tool maximizes what your hardware can hear, but the
antenna and radio are what set the ceiling:

- **WiFi**: use a high-gain adapter (e.g. Alfa AWUS036ACH/AWUS1900 with
  a directional panel or Yagi antenna) instead of a stock USB dongle.
  Channel hopping (`--channels`, on by default) widens *which* networks
  you see across the whole band, not how far any one signal reaches.
- **BLE**: a USB BLE dongle with an external antenna connector hears
  much farther than the Pi's onboard chip; BLE's own range is inherently
  shorter than WiFi's regardless of antenna.
- Elevate the antenna and remove line-of-sight obstructions — this
  matters more for real-world range than any software setting.

## What gets logged

Each JSONL line is one observation. WiFi records include
`frame_type`, `bssid`, `client_mac`, `ssid`, `channel`, `rssi`,
`encryption`, `vendor`. BLE records include `address`, `name`, `rssi`,
`tx_power`, `manufacturer_ids`, `service_uuids`, `vendor`. `report`
turns a log into a markdown table per access point / probing client /
BLE device (packet counts, strongest RSSI seen, first/last seen), plus
optional CSV export for further analysis in a spreadsheet or notebook.

---

# netwatch: monitoring console

A dedicated web console that puts full network monitoring in one dashboard:
IP host **wake/sleep** transitions (active ICMP polling, with timestamps)
alongside the **MAC/BSSID connection records** captured by `rf_sniffer`
(passive WiFi + BLE) — each table with its own data-filter options.

## Setup

```bash
pip install -r requirements.txt   # installs Flask
```

## Usage

```bash
# Watch a list of hosts (one "ip" or "ip,hostname" per line) and the
# rf_sniffer logs in logs/, on http://127.0.0.1:8080/
python -m netwatch serve --hosts hosts.txt --rf-log-dir logs/

# Or pass targets inline, and/or a specific rf_sniffer log file
python -m netwatch serve --host 10.0.0.1:router --host 10.0.0.2 \
    --rf-log logs/combined_20260101T000000Z.jsonl --port 8080
```

`serve` starts a background poller that pings every configured host on
`--interval` seconds (default 30) and logs every up→down ("sleep") or
down→up ("wake") transition, timestamped, to `<ip-log-dir>/ip_events_*.jsonl`
— the same append-only JSONL format `rf_sniffer` uses. It also tails
whichever `rf_sniffer` WiFi/BLE logs you point it at (`--rf-log`, repeatable,
and/or `--rf-log-dir` to pick up a whole folder), so captures from an
in-progress or finished `rf_sniffer` session show up live.

The console (`/`) shows:

- **IP monitor** — current up/down status per host, plus the full wake/sleep
  history, filterable by IP/hostname, status, and time range.
- **MAC/BSSID connection records** — every WiFi and BLE observation, unified
  into one table, filterable by MAC/address, BSSID, SSID/name, vendor,
  encryption, WiFi-vs-BLE, and a free-text search across all fields.

The same data is available as JSON for scripting: `GET /api/ip/status`,
`/api/ip/events`, `/api/connections`, `/api/summary` (all accept the same
filters as query parameters).
