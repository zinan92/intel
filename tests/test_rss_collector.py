"""Tests for config-driven RSS collector."""
from unittest.mock import MagicMock, patch

import pytest
from collectors.rss import RSSCollector

FAKE_FEEDS = [
    {"name": "Test Blog", "url": "https://example.com/feed.xml", "category": "llm"},
    {"name": "Broken Feed", "url": "https://broken.example.com/feed.xml", "category": "crypto"},
]

FAKE_ENTRY = MagicMock()
FAKE_ENTRY.link = "https://example.com/post/1"
FAKE_ENTRY.title = "Test Post"
FAKE_ENTRY.summary = "Some content"
FAKE_ENTRY.published_parsed = (2024, 1, 15, 10, 0, 0, 0, 0, 0)
FAKE_ENTRY.author = ""
FAKE_ENTRY.tags = []

GOOD_FEED = MagicMock()
GOOD_FEED.entries = [FAKE_ENTRY]
GOOD_FEED.bozo = False

EMPTY_FEED = MagicMock()
EMPTY_FEED.entries = []
EMPTY_FEED.bozo = False


def test_rss_collect_returns_list():
    with patch("collectors.rss.feedparser.parse", return_value=EMPTY_FEED), \
         patch("collectors.rss.config.RSS_FEEDS", FAKE_FEEDS):
        assert isinstance(RSSCollector().collect(), list)


def test_rss_parses_entry_to_dict():
    with patch("collectors.rss.feedparser.parse", return_value=GOOD_FEED), \
         patch("collectors.rss.config.RSS_FEEDS", [FAKE_FEEDS[0]]):
        result = RSSCollector().collect()
    assert len(result) == 1
    a = result[0]
    assert a["source"] == "rss"
    assert a["title"] == "Test Post"
    assert a["url"] == "https://example.com/post/1"


def test_rss_category_in_tags():
    with patch("collectors.rss.feedparser.parse", return_value=GOOD_FEED), \
         patch("collectors.rss.config.RSS_FEEDS", [FAKE_FEEDS[0]]):
        result = RSSCollector().collect()
    assert "llm" in result[0]["tags"]


def test_rss_source_id_deterministic():
    with patch("collectors.rss.feedparser.parse", return_value=GOOD_FEED), \
         patch("collectors.rss.config.RSS_FEEDS", [FAKE_FEEDS[0]]):
        r1 = RSSCollector().collect()
    with patch("collectors.rss.feedparser.parse", return_value=GOOD_FEED), \
         patch("collectors.rss.config.RSS_FEEDS", [FAKE_FEEDS[0]]):
        r2 = RSSCollector().collect()
    assert r1[0]["source_id"] == r2[0]["source_id"]


def test_rss_broken_feed_skipped_gracefully():
    def side_effect(url, **kw):
        if "broken" in url:
            raise Exception("timeout")
        return GOOD_FEED
    with patch("collectors.rss.feedparser.parse", side_effect=side_effect), \
         patch("collectors.rss.config.RSS_FEEDS", FAKE_FEEDS):
        result = RSSCollector().collect()
    assert len(result) == 1  # only good feed result
