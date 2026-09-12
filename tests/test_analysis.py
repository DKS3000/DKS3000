from pathlib import Path

from instagram_analyzer.analysis import analyze
from instagram_analyzer.export_parser import parse_export
from instagram_analyzer.report import to_html, to_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export"


def _analyze():
    return analyze(parse_export(str(FIXTURE)))


def test_basic_counts():
    result = _analyze()
    assert result.total_posts == 3
    assert result.follower_count == 3
    assert result.following_count == 2


def test_hashtags_and_keywords():
    result = _analyze()
    hashtag_names = [h for h, _ in result.top_hashtags]
    assert "newyear" in hashtag_names
    assert "hiking" in hashtag_names
    mention_names = [m for m, _ in result.top_mentions]
    assert "friendaccount" in mention_names


def test_network_insights():
    result = _analyze()
    assert result.not_following_back == ["dave"]
    assert result.not_followed_back == ["bob", "carol"]


def test_engagement_given():
    result = _analyze()
    assert result.comments_given_count == 3
    assert result.likes_given_count == 2
    assert result.top_comment_targets[0] == ("alice", 2)


def test_reports_render_without_error():
    result = _analyze()
    md = to_markdown(result)
    html = to_html(result)
    assert "sample_user" in md
    assert "sample_user" in html
    assert "<html" in html
