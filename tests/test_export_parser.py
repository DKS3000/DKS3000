from pathlib import Path

from instagram_analyzer.export_parser import parse_export

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export"


def test_parse_profile_info():
    profile = parse_export(str(FIXTURE))
    assert profile.username == "sample_user"
    assert profile.name == "Sample User"
    assert profile.bio == "Just here having fun"
    assert profile.private is False


def test_parse_posts():
    profile = parse_export(str(FIXTURE))
    assert len(profile.posts) == 3
    assert profile.posts[0].timestamp < profile.posts[-1].timestamp
    captions = [p.caption for p in profile.posts]
    assert any("hike" in c for c in captions)
    assert any(p.media_type == "video" for p in profile.posts)


def test_parse_followers_following():
    profile = parse_export(str(FIXTURE))
    assert set(profile.followers) == {"alice", "bob", "carol"}
    assert set(profile.following) == {"alice", "dave"}
    assert profile.follower_count == 3
    assert profile.following_count == 2


def test_parse_comments_and_likes():
    profile = parse_export(str(FIXTURE))
    assert len(profile.comments_given) == 3
    assert len(profile.likes_given) == 2
    targets = {c.target for c in profile.comments_given}
    assert targets == {"alice", "bob"}


def test_missing_export_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        parse_export("/no/such/path")
