"""Small text helpers: mojibake repair, hashtag/mention extraction, keyword counts."""

import re
from collections import Counter
from typing import Iterable, List, Tuple

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@([\w.]+)")
WORD_RE = re.compile(r"[A-Za-z']+")

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "is", "it", "this", "that", "with", "as", "at", "by", "be", "are",
    "was", "were", "i", "you", "we", "my", "your", "our", "me", "so",
    "just", "up", "out", "all", "not", "if", "when", "from", "im", "its",
    "have", "has", "had", "do", "did", "does", "will", "can", "no", "yes",
}


def fix_mojibake(text: str) -> str:
    """Instagram's JSON export escapes non-ASCII text as UTF-8 bytes read as
    Latin-1 (a known export bug), so emoji/accents come out garbled. Undo it
    when possible; leave the text alone if it wasn't actually mangled."""
    if not text:
        return text
    try:
        return text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def extract_hashtags(captions: Iterable[str]) -> Counter:
    counter: Counter = Counter()
    for caption in captions:
        if caption:
            counter.update(m.lower() for m in HASHTAG_RE.findall(caption))
    return counter


def extract_mentions(captions: Iterable[str]) -> Counter:
    counter: Counter = Counter()
    for caption in captions:
        if caption:
            counter.update(m.lower() for m in MENTION_RE.findall(caption))
    return counter


def top_keywords(captions: Iterable[str], limit: int = 20) -> List[Tuple[str, int]]:
    counter: Counter = Counter()
    for caption in captions:
        if not caption:
            continue
        words = (w.lower() for w in WORD_RE.findall(caption))
        counter.update(w for w in words if len(w) > 2 and w not in STOPWORDS)
    return counter.most_common(limit)
