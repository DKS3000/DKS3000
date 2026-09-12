"""Common data model shared by both data sources (data export + Graph API)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Post:
    id: str
    caption: str
    timestamp: Optional[datetime]
    media_type: str = "unknown"
    like_count: Optional[int] = None
    comment_count: Optional[int] = None


@dataclass
class Interaction:
    """A comment or like given to someone else's content."""

    target: Optional[str]
    text: Optional[str]
    timestamp: Optional[datetime]


@dataclass
class ProfileData:
    source: str  # "export" or "graph_api"
    username: Optional[str] = None
    name: Optional[str] = None
    bio: Optional[str] = None
    private: Optional[bool] = None
    follower_count: Optional[int] = None
    following_count: Optional[int] = None
    posts: List[Post] = field(default_factory=list)
    followers: List[str] = field(default_factory=list)
    following: List[str] = field(default_factory=list)
    comments_given: List[Interaction] = field(default_factory=list)
    likes_given: List[Interaction] = field(default_factory=list)
