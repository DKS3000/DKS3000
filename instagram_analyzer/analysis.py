"""Turns a ProfileData into an organized set of statistics."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import ProfileData
from .text_utils import extract_hashtags, extract_mentions, top_keywords

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class AnalysisResult:
    source: str
    username: Optional[str]
    name: Optional[str]
    bio: Optional[str]
    private: Optional[bool]

    total_posts: int
    date_range: Optional[Tuple[str, str]]
    posts_per_weekday: Dict[str, int]
    posts_per_hour: Dict[int, int]
    posts_per_month: Dict[str, int]
    busiest_weekday: Optional[str]
    busiest_hour: Optional[int]
    avg_caption_length: float
    posts_with_caption_pct: float

    top_hashtags: List[Tuple[str, int]]
    top_mentions: List[Tuple[str, int]]
    top_keywords: List[Tuple[str, int]]

    follower_count: Optional[int]
    following_count: Optional[int]
    not_following_back: List[str] = field(default_factory=list)  # you follow, they don't follow you
    not_followed_back: List[str] = field(default_factory=list)  # they follow you, you don't follow them

    comments_given_count: int = 0
    likes_given_count: int = 0
    top_comment_targets: List[Tuple[str, int]] = field(default_factory=list)
    top_like_targets: List[Tuple[str, int]] = field(default_factory=list)

    top_posts_by_engagement: List[dict] = field(default_factory=list)


def analyze(profile: ProfileData) -> AnalysisResult:
    posts = profile.posts
    captions = [p.caption for p in posts]
    timestamped = [p for p in posts if p.timestamp]

    posts_per_weekday = Counter(WEEKDAYS[p.timestamp.weekday()] for p in timestamped)
    posts_per_hour = Counter(p.timestamp.hour for p in timestamped)
    posts_per_month = Counter(p.timestamp.strftime("%Y-%m") for p in timestamped)

    date_range = None
    if timestamped:
        dates = sorted(p.timestamp for p in timestamped)
        date_range = (dates[0].date().isoformat(), dates[-1].date().isoformat())

    non_empty_captions = [c for c in captions if c]
    avg_caption_length = (
        sum(len(c) for c in non_empty_captions) / len(non_empty_captions) if non_empty_captions else 0.0
    )
    posts_with_caption_pct = (len(non_empty_captions) / len(posts) * 100) if posts else 0.0

    followers_set = set(profile.followers)
    following_set = set(profile.following)
    not_following_back = sorted(following_set - followers_set)
    not_followed_back = sorted(followers_set - following_set)

    comment_targets = Counter(i.target for i in profile.comments_given if i.target)
    like_targets = Counter(i.target for i in profile.likes_given if i.target)

    top_posts = []
    scored = [p for p in posts if p.like_count is not None or p.comment_count is not None]
    if scored:
        scored.sort(key=lambda p: (p.like_count or 0) + (p.comment_count or 0), reverse=True)
        top_posts = [
            {
                "id": p.id,
                "caption": (p.caption or "")[:80],
                "timestamp": p.timestamp.isoformat() if p.timestamp else None,
                "like_count": p.like_count,
                "comment_count": p.comment_count,
            }
            for p in scored[:10]
        ]

    return AnalysisResult(
        source=profile.source,
        username=profile.username,
        name=profile.name,
        bio=profile.bio,
        private=profile.private,
        total_posts=len(posts),
        date_range=date_range,
        posts_per_weekday=dict(posts_per_weekday),
        posts_per_hour=dict(posts_per_hour),
        posts_per_month=dict(sorted(posts_per_month.items())),
        busiest_weekday=posts_per_weekday.most_common(1)[0][0] if posts_per_weekday else None,
        busiest_hour=posts_per_hour.most_common(1)[0][0] if posts_per_hour else None,
        avg_caption_length=round(avg_caption_length, 1),
        posts_with_caption_pct=round(posts_with_caption_pct, 1),
        top_hashtags=extract_hashtags(captions).most_common(20),
        top_mentions=extract_mentions(captions).most_common(20),
        top_keywords=top_keywords(captions, limit=20),
        follower_count=profile.follower_count,
        following_count=profile.following_count,
        not_following_back=not_following_back,
        not_followed_back=not_followed_back,
        comments_given_count=len(profile.comments_given),
        likes_given_count=len(profile.likes_given),
        top_comment_targets=comment_targets.most_common(10),
        top_like_targets=like_targets.most_common(10),
        top_posts_by_engagement=top_posts,
    )
