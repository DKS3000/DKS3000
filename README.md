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
