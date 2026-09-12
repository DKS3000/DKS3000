"""Parses Instagram's official 'Download Your Information' data export (JSON
format) into the common ProfileData model.

Get your export from: Instagram app/site -> Settings -> Accounts Center ->
Your information and permissions -> Download your information -> choose
JSON format. Point this parser at the extracted folder.

Instagram has changed this export's exact layout over time, so every lookup
here is best-effort: missing files are skipped rather than treated as
errors, and each JSON shape is read defensively.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import Interaction, Post, ProfileData
from .text_utils import fix_mojibake


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _glob_first_dir(root: Path, *name_options: str) -> Optional[Path]:
    for name in name_options:
        matches = list(root.rglob(name))
        if matches:
            return matches[0]
    return None


def _string_map(entry: Dict) -> Dict[str, str]:
    """Flattens Instagram's {"string_map_data": {"Key": {"value": "..."}}}
    shape into a plain {key: value} dict."""
    out = {}
    for key, val in entry.get("string_map_data", {}).items():
        out[key] = fix_mojibake(val.get("value", "")) if isinstance(val, dict) else val
    return out


def _string_list(entry: Dict) -> List[Dict[str, str]]:
    return entry.get("string_list_data", []) or []


def parse_profile_info(root: Path, profile: ProfileData) -> None:
    path = _glob_first_dir(root, "personal_information.json")
    data = _load_json(path) if path else None
    if not data:
        return
    entries = data.get("profile_user") or data.get("profile_account_insights") or []
    if not entries:
        return
    fields = _string_map(entries[0])
    profile.username = fields.get("Username") or fields.get("String List Data")
    profile.name = fields.get("Name")
    profile.bio = fields.get("Bio")
    private = fields.get("Private Account")
    if private is not None:
        profile.private = str(private).lower() in ("true", "yes")


def parse_posts(root: Path, profile: ProfileData) -> None:
    candidates: List[Path] = []
    for pattern in ("posts_*.json", "posts.json"):
        candidates.extend(sorted(root.rglob(pattern)))
    seen_paths = set()
    for path in candidates:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        data = _load_json(path)
        if not isinstance(data, list):
            continue
        for i, item in enumerate(data):
            caption = fix_mojibake(item.get("title", "") or "")
            media_list = item.get("media", [item]) or [item]
            timestamp = None
            media_type = "unknown"
            for media in media_list:
                ts = media.get("creation_timestamp")
                if ts:
                    from datetime import datetime, timezone

                    timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
                if not caption:
                    caption = fix_mojibake(media.get("title", "") or "")
                uri = media.get("uri", "")
                if uri:
                    media_type = "video" if uri.lower().endswith((".mp4", ".mov")) else "photo"
                break
            profile.posts.append(
                Post(id=f"{path.name}:{i}", caption=caption, timestamp=timestamp, media_type=media_type)
            )


def _parse_relationship_file(path: Optional[Path], list_key_hints: List[str]) -> List[str]:
    data = _load_json(path) if path else None
    if data is None:
        return []
    entries: List[Dict] = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        for hint in list_key_hints:
            if hint in data:
                entries = data[hint]
                break
        else:
            entries = next((v for v in data.values() if isinstance(v, list)), [])
    usernames = []
    for entry in entries:
        for item in _string_list(entry):
            value = item.get("value")
            if value:
                usernames.append(value)
    return usernames


def parse_followers_following(root: Path, profile: ProfileData) -> None:
    followers_path = _glob_first_dir(root, "followers_1.json", "followers.json")
    following_path = _glob_first_dir(root, "following.json")
    profile.followers = _parse_relationship_file(followers_path, ["relationships_followers"])
    profile.following = _parse_relationship_file(following_path, ["relationships_following"])
    if profile.followers:
        profile.follower_count = len(profile.followers)
    if profile.following:
        profile.following_count = len(profile.following)


def parse_comments_given(root: Path, profile: ProfileData) -> None:
    path = _glob_first_dir(root, "post_comments_1.json", "post_comments.json")
    data = _load_json(path) if path else None
    if not isinstance(data, list):
        return
    from datetime import datetime, timezone

    for entry in data:
        fields = _string_map(entry)
        text = fields.get("Comment")
        target = fields.get("Media Owner")
        ts_raw = fields.get("Time")
        timestamp = None
        if ts_raw:
            try:
                timestamp = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
            except (ValueError, TypeError):
                pass
        if not timestamp:
            for item in _string_list(entry):
                if item.get("timestamp"):
                    timestamp = datetime.fromtimestamp(item["timestamp"], tz=timezone.utc)
                    break
        profile.comments_given.append(Interaction(target=target, text=text, timestamp=timestamp))


def parse_likes_given(root: Path, profile: ProfileData) -> None:
    path = _glob_first_dir(root, "liked_posts.json")
    data = _load_json(path) if path else None
    if not isinstance(data, dict):
        return
    from datetime import datetime, timezone

    entries = data.get("likes_media_likes", [])
    for entry in entries:
        target = entry.get("title")
        for item in _string_list(entry):
            ts = item.get("timestamp")
            timestamp = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            profile.likes_given.append(Interaction(target=target, text=None, timestamp=timestamp))


def parse_export(export_dir: str) -> ProfileData:
    """Parses an extracted Instagram data-export folder into a ProfileData."""
    root = Path(export_dir)
    if not root.exists():
        raise FileNotFoundError(f"Export folder not found: {export_dir}")

    profile = ProfileData(source="export")
    parse_profile_info(root, profile)
    parse_posts(root, profile)
    parse_followers_following(root, profile)
    parse_comments_given(root, profile)
    parse_likes_given(root, profile)

    from datetime import datetime, timezone

    epoch = datetime.fromtimestamp(0, tz=timezone.utc)
    profile.posts.sort(key=lambda p: p.timestamp or epoch)
    return profile
