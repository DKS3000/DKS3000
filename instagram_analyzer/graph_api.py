"""Optional live data source: Instagram Graph API (for your own Business or
Creator account). This is the official, ToS-compliant way to pull live posts
and engagement insights instead of a one-off data export.

Setup (do this once, on Meta's side, before this module is useful):
  1. Convert your Instagram account to a Business or Creator account and
     link it to a Facebook Page.
  2. Create an app at https://developers.facebook.com/apps and add the
     "Instagram Graph API" product.
  3. Generate a long-lived Page/User access token with the
     instagram_basic + pages_show_list (+ instagram_manage_insights for
     engagement metrics) permissions.
  4. Find your Instagram Business Account ID (via GET /me/accounts then
     GET /{page-id}?fields=instagram_business_account).
  5. Export IG_ACCESS_TOKEN and IG_BUSINESS_ACCOUNT_ID as environment
     variables (or pass them in directly) and run:
         python -m instagram_analyzer fetch --out reports/

`requests` is only imported when this module is actually used, so the
export-based analyzer works without it installed.
"""

import os
from datetime import datetime, timezone
from typing import Optional

from .models import Post, ProfileData

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def fetch_profile(access_token: Optional[str] = None, business_account_id: Optional[str] = None) -> ProfileData:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "The 'requests' package is required for Graph API access. Install it with: pip install requests"
        ) from exc

    token = access_token or os.environ.get("IG_ACCESS_TOKEN")
    account_id = business_account_id or os.environ.get("IG_BUSINESS_ACCOUNT_ID")
    if not token or not account_id:
        raise RuntimeError(
            "Set IG_ACCESS_TOKEN and IG_BUSINESS_ACCOUNT_ID (env vars or arguments) before fetching."
        )

    profile = ProfileData(source="graph_api")

    account = requests.get(
        f"{GRAPH_API_BASE}/{account_id}",
        params={
            "fields": "username,name,biography,followers_count,follows_count",
            "access_token": token,
        },
        timeout=30,
    ).json()
    _raise_if_error(account)
    profile.username = account.get("username")
    profile.name = account.get("name")
    profile.bio = account.get("biography")
    profile.follower_count = account.get("followers_count")
    profile.following_count = account.get("follows_count")

    media_url = f"{GRAPH_API_BASE}/{account_id}/media"
    params = {
        "fields": "id,caption,timestamp,media_type,like_count,comments_count",
        "access_token": token,
        "limit": 100,
    }
    while media_url:
        page = requests.get(media_url, params=params, timeout=30).json()
        _raise_if_error(page)
        for item in page.get("data", []):
            profile.posts.append(
                Post(
                    id=item["id"],
                    caption=item.get("caption", ""),
                    timestamp=_parse_ts(item.get("timestamp")),
                    media_type=(item.get("media_type") or "unknown").lower(),
                    like_count=item.get("like_count"),
                    comment_count=item.get("comments_count"),
                )
            )
        media_url = page.get("paging", {}).get("next")
        params = None  # `next` already includes all query params

    return profile


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _raise_if_error(payload: dict) -> None:
    if isinstance(payload, dict) and "error" in payload:
        raise RuntimeError(f"Instagram Graph API error: {payload['error']}")
