"""Tests for Reddit collector — RSS parsing and deduplication."""
from unittest.mock import MagicMock, patch

import pytest
from collectors.reddit import RedditCollector


def _make_entry(title, link, entry_id=None, summary="", author="testuser"):
    e = MagicMock()
    e.title = title
    e.link = link
    e.id = entry_id or link
    e.summary = summary
    e.author = author
    e.author_detail = None
    e.published_parsed = (2024, 1, 15, 10, 0, 0, 0, 0, 0)
    e.updated_parsed = None
    e.tags = []
    return e


FAKE_SUBS = [
    {"subreddit": "MachineLearning", "category": "llm"},
    {"subreddit": "Bitcoin", "category": "crypto"},
]


def _mock_feed_for(subreddit, entries):
    feed = MagicMock()
    feed.entries = entries
    feed.bozo = False
    return feed


def test_reddit_collect_returns_list():
    empty_feed = MagicMock()
    empty_feed.entries = []
    with patch("collectors.reddit.feedparser.parse", return_value=empty_feed), \
         patch("collectors.reddit.config.REDDIT_SUBREDDITS", FAKE_SUBS):
        result = RedditCollector().collect()
    assert isinstance(result, list)


def test_reddit_parses_entry():
    entry = _make_entry("Great paper on LLMs", "https://reddit.com/r/ML/post1", entry_id="t3_abc")
    feed = MagicMock()
    feed.entries = [entry]
    feed.bozo = False
    with patch("collectors.reddit.feedparser.parse", return_value=feed), \
         patch("collectors.reddit.config.REDDIT_SUBREDDITS", [FAKE_SUBS[0]]):
        result = RedditCollector().collect()
    assert len(result) == 1
    a = result[0]
    assert a["source"] == "reddit"
    assert a["title"] == "Great paper on LLMs"
    assert a["url"] == "https://reddit.com/r/ML/post1"


def test_reddit_category_in_tags():
    entry = _make_entry("Something", "https://reddit.com/r/ML/post2")
    feed = MagicMock()
    feed.entries = [entry]
    feed.bozo = False
    with patch("collectors.reddit.feedparser.parse", return_value=feed), \
         patch("collectors.reddit.config.REDDIT_SUBREDDITS", [FAKE_SUBS[0]]):
        result = RedditCollector().collect()
    assert "llm" in result[0]["tags"]


def test_reddit_deduplicates_across_subreddits():
    shared_url = "https://reddit.com/r/shared/post99"
    entry1 = _make_entry("Post A", shared_url, entry_id="t3_001")
    entry2 = _make_entry("Post A", shared_url, entry_id="t3_001")
    feeds = [
        MagicMock(entries=[entry1], bozo=False),
        MagicMock(entries=[entry2], bozo=False),
    ]
    call_count = [0]
    def feed_side_effect(url, **kw):
        result = feeds[call_count[0]]
        call_count[0] += 1
        return result
    with patch("collectors.reddit.feedparser.parse", side_effect=feed_side_effect), \
         patch("collectors.reddit.config.REDDIT_SUBREDDITS", FAKE_SUBS):
        result = RedditCollector().collect()
    urls = [a["url"] for a in result]
    assert urls.count(shared_url) == 1


def test_reddit_source_id_deterministic():
    entry = _make_entry("Title", "https://reddit.com/r/ML/post3", entry_id="t3_xyz")
    feed = MagicMock()
    feed.entries = [entry]
    feed.bozo = False
    with patch("collectors.reddit.feedparser.parse", return_value=feed), \
         patch("collectors.reddit.config.REDDIT_SUBREDDITS", [FAKE_SUBS[0]]):
        r1 = RedditCollector().collect()
    with patch("collectors.reddit.feedparser.parse", return_value=feed), \
         patch("collectors.reddit.config.REDDIT_SUBREDDITS", [FAKE_SUBS[0]]):
        r2 = RedditCollector().collect()
    assert r1[0]["source_id"] == r2[0]["source_id"]


def test_reddit_failed_subreddit_continues():
    good_entry = _make_entry("Good Post", "https://reddit.com/r/Bitcoin/post1")
    good_feed = MagicMock(entries=[good_entry], bozo=False)

    def side_effect(url, **kw):
        if "MachineLearning" in url:
            raise Exception("network error")
        return good_feed

    with patch("collectors.reddit.feedparser.parse", side_effect=side_effect), \
         patch("collectors.reddit.config.REDDIT_SUBREDDITS", FAKE_SUBS):
        result = RedditCollector().collect()
    assert len(result) == 1
    assert result[0]["url"] == "https://reddit.com/r/Bitcoin/post1"
