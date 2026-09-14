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

# Turn a captured session into a readable report + open a dashboard
python -m rf_sniffer report --log logs/combined_20260101T000000Z.jsonl \
    --out reports/session.md --csv reports/session.csv \
    --html reports/session.html --open
```

Add `--report path/to/out.md` / `--html path/to/out.html` to
`wifi`/`ble`/`both` to generate the report/dashboard automatically when
the capture finishes, plus `--open` to launch the dashboard in a
browser right away.

## Opening the dashboard

`--html` writes a single self-contained `.html` file (no server, no
external assets, no network access needed) with summary cards, and a
sortable/filterable table per access point, probing client, and BLE
device. To open it:

- **On the Pi with a desktop**, `--open` launches it in the default
  browser automatically, or double-click the file / run
  `xdg-open reports/session.html`.
- **Headless Pi (SSH only)**, copy it to a machine that has a browser:
  `scp pi@raspberrypi.local:~/reports/session.html .` then open it
  locally — or serve the folder and browse to it from another device
  on the network: `python -m http.server 8000 --directory reports`
  then visit `http://raspberrypi.local:8000/session.html`.

Click any column header to sort a table; the search box above each
table filters its rows live (e.g. type a vendor name or partial MAC).

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
