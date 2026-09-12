"""Renders an AnalysisResult as an organized Markdown report and a
self-contained HTML dashboard (no external assets, works offline)."""

from pathlib import Path
from typing import List, Tuple

from .analysis import AnalysisResult


def _bar(count: int, max_count: int, width: int = 30) -> str:
    if max_count <= 0:
        return ""
    filled = round((count / max_count) * width)
    return "#" * filled


def _table(rows: List[Tuple[str, int]], headers: Tuple[str, str]) -> str:
    lines = [f"| {headers[0]} | {headers[1]} |", "| --- | --- |"]
    for label, count in rows:
        lines.append(f"| {label} | {count} |")
    return "\n".join(lines) if rows else "_none found_"


def to_markdown(result: AnalysisResult) -> str:
    lines = []
    lines.append(f"# Instagram Profile Report{f' — @{result.username}' if result.username else ''}")
    lines.append(f"\n_Source: {result.source}_\n")

    lines.append("## Profile")
    lines.append(f"- **Name:** {result.name or 'n/a'}")
    lines.append(f"- **Bio:** {result.bio or 'n/a'}")
    lines.append(f"- **Private account:** {result.private if result.private is not None else 'n/a'}")
    lines.append(f"- **Followers:** {result.follower_count if result.follower_count is not None else 'n/a'}")
    lines.append(f"- **Following:** {result.following_count if result.following_count is not None else 'n/a'}")

    lines.append("\n## Content overview")
    lines.append(f"- **Total posts:** {result.total_posts}")
    if result.date_range:
        lines.append(f"- **Active from:** {result.date_range[0]} to {result.date_range[1]}")
    lines.append(f"- **Posts with a caption:** {result.posts_with_caption_pct}%")
    lines.append(f"- **Average caption length:** {result.avg_caption_length} characters")
    if result.busiest_weekday:
        lines.append(f"- **Most active weekday:** {result.busiest_weekday}")
    if result.busiest_hour is not None:
        lines.append(f"- **Most active hour (UTC):** {result.busiest_hour}:00")

    if result.posts_per_weekday:
        lines.append("\n### Posting rhythm by weekday")
        max_count = max(result.posts_per_weekday.values())
        for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            count = result.posts_per_weekday.get(day, 0)
            lines.append(f"- {day}: {_bar(count, max_count)} ({count})")

    if result.top_hashtags:
        lines.append("\n## Top hashtags")
        lines.append(_table(result.top_hashtags, ("Hashtag", "Uses")))

    if result.top_mentions:
        lines.append("\n## Top mentions")
        lines.append(_table(result.top_mentions, ("Mention", "Uses")))

    if result.top_keywords:
        lines.append("\n## Top caption keywords")
        lines.append(_table(result.top_keywords, ("Word", "Count")))

    if result.top_posts_by_engagement:
        lines.append("\n## Top performing posts")
        lines.append("| Caption | Likes | Comments | Date |")
        lines.append("| --- | --- | --- | --- |")
        for p in result.top_posts_by_engagement:
            lines.append(
                f"| {p['caption']} | {p['like_count']} | {p['comment_count']} | {p['timestamp'] or 'n/a'} |"
            )

    lines.append("\n## Your engagement with others")
    lines.append(f"- **Comments you've given:** {result.comments_given_count}")
    lines.append(f"- **Likes you've given:** {result.likes_given_count}")
    if result.top_comment_targets:
        lines.append("\n### Accounts you comment on most")
        lines.append(_table(result.top_comment_targets, ("Account", "Comments")))
    if result.top_like_targets:
        lines.append("\n### Accounts you like most")
        lines.append(_table(result.top_like_targets, ("Account", "Likes")))

    if result.not_following_back or result.not_followed_back:
        lines.append("\n## Network insights")
        lines.append(f"- **You follow but they don't follow back:** {len(result.not_following_back)}")
        lines.append(f"- **They follow you but you don't follow back:** {len(result.not_followed_back)}")

    return "\n".join(lines) + "\n"


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Instagram Profile Report{title_suffix}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         max-width: 900px; margin: 0 auto; padding: 24px 16px; line-height: 1.5; }}
  h1 {{ margin-bottom: 4px; }}
  .muted {{ opacity: .65; font-size: .9em; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0; }}
  .card {{ border: 1px solid currentColor; border-radius: 10px; padding: 14px; opacity: .95; }}
  .card .n {{ font-size: 1.6em; font-weight: 700; display: block; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid rgba(128,128,128,.3); }}
  .bar-row {{ display: flex; align-items: center; gap: 8px; margin: 4px 0; }}
  .bar-label {{ width: 40px; }}
  .bar-track {{ flex: 1; background: rgba(128,128,128,.2); border-radius: 4px; height: 14px; overflow: hidden; }}
  .bar-fill {{ background: #E1306C; height: 100%; }}
  section {{ margin-bottom: 32px; }}
</style>
</head>
<body>
<h1>Instagram Profile Report{title_suffix}</h1>
<p class="muted">Source: {source}</p>

<section class="grid">
  <div class="card"><span class="n">{total_posts}</span>Posts</div>
  <div class="card"><span class="n">{follower_count}</span>Followers</div>
  <div class="card"><span class="n">{following_count}</span>Following</div>
  <div class="card"><span class="n">{posts_with_caption_pct}%</span>Have a caption</div>
</section>

<section>
<h2>Profile</h2>
<p><b>Name:</b> {name}<br><b>Bio:</b> {bio}<br><b>Private:</b> {private}</p>
</section>

<section>
<h2>Posting rhythm by weekday</h2>
{weekday_bars}
</section>

<section>
<h2>Top hashtags</h2>
{hashtag_table}
</section>

<section>
<h2>Top caption keywords</h2>
{keyword_table}
</section>

<section>
<h2>Your engagement with others</h2>
<p><b>Comments given:</b> {comments_given_count} &nbsp; <b>Likes given:</b> {likes_given_count}</p>
{comment_targets_table}
</section>

<section>
<h2>Network insights</h2>
<p><b>You follow, they don't follow back:</b> {not_following_back}<br>
<b>They follow you, you don't follow back:</b> {not_followed_back}</p>
</section>

</body>
</html>
"""


def _html_table(rows: List[Tuple[str, int]], headers: Tuple[str, str]) -> str:
    if not rows:
        return "<p><i>none found</i></p>"
    body = "".join(f"<tr><td>{label}</td><td>{count}</td></tr>" for label, count in rows)
    return f"<table><tr><th>{headers[0]}</th><th>{headers[1]}</th></tr>{body}</table>"


def to_html(result: AnalysisResult) -> str:
    max_count = max(result.posts_per_weekday.values()) if result.posts_per_weekday else 0
    bars = []
    for day in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
        count = result.posts_per_weekday.get(day, 0)
        pct = round((count / max_count) * 100) if max_count else 0
        bars.append(
            f'<div class="bar-row"><span class="bar-label">{day}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f"<span>{count}</span></div>"
        )

    return _HTML_TEMPLATE.format(
        title_suffix=f" — @{result.username}" if result.username else "",
        source=result.source,
        total_posts=result.total_posts,
        follower_count=result.follower_count if result.follower_count is not None else "n/a",
        following_count=result.following_count if result.following_count is not None else "n/a",
        posts_with_caption_pct=result.posts_with_caption_pct,
        name=result.name or "n/a",
        bio=result.bio or "n/a",
        private=result.private if result.private is not None else "n/a",
        weekday_bars="\n".join(bars),
        hashtag_table=_html_table(result.top_hashtags, ("Hashtag", "Uses")),
        keyword_table=_html_table(result.top_keywords, ("Word", "Count")),
        comments_given_count=result.comments_given_count,
        likes_given_count=result.likes_given_count,
        comment_targets_table=_html_table(result.top_comment_targets, ("Account", "Comments")),
        not_following_back=len(result.not_following_back),
        not_followed_back=len(result.not_followed_back),
    )


def write_report(result: AnalysisResult, out_dir: str) -> Tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / "profile_report.md"
    html_path = out / "profile_report.html"
    md_path.write_text(to_markdown(result), encoding="utf-8")
    html_path.write_text(to_html(result), encoding="utf-8")
    return md_path, html_path
