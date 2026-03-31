"""Tests for source-type adapters.

Each adapter accepts a source registry record (as a dict) and produces
normalized article dicts. Tests use mocking to avoid network calls.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sources.adapters import collect_from_source, get_adapter


class TestGetAdapter:
    """get_adapter returns a callable for known source types."""

    def test_known_types(self):
        for stype in ["rss", "reddit", "github_release", "website_monitor", "social_kol",
                       "hackernews", "xueqiu", "yahoo_finance", "google_news", "github_trending"]:
            adapter = get_adapter(stype)
            assert adapter is not None, f"No adapter for {stype}"
            assert callable(adapter)

    def test_unknown_type_returns_none(self):
        assert get_adapter("nonexistent_type") is None


class TestCollectFromSource:
    """collect_from_source dispatches to the right adapter."""

    def test_unknown_type_returns_empty(self):
        record = _record("unknown:x", "unknown_type", {})
        articles, result = collect_from_source(record)
        assert articles == []
        assert result.status == "error"

    @patch("tenacity.nap.time.sleep")
    def test_returns_list(self, mock_sleep):
        """Result is always a tuple of (list, CollectorResult)."""
        with patch("sources.adapters._adapt_rss", return_value=[{"title": "Test"}]):
            record = _record("rss:test", "rss", {"url": "http://example.com/feed"})
            articles, result = collect_from_source(record)
            assert isinstance(articles, list)


class TestRSSAdapter:
    """RSS adapter delegates to RSSCollector._fetch_feed."""

    def test_rss_adapter_uses_config_url(self):
        """The adapter should use the URL from the source config, not global config."""
        with patch("collectors.rss.RSSCollector._fetch_feed") as mock_fetch:
            mock_fetch.return_value = [{"title": "T", "source": "rss", "source_id": "rss_x",
                                         "url": "http://example.com/post", "content": "",
                                         "tags": [], "score": 0, "published_at": None, "author": ""}]
            from sources.adapters import _adapt_rss
            articles = _adapt_rss(_record("rss:test", "rss", {"url": "http://example.com/feed", "name": "Test"}))
            # Verify _fetch_feed was called with a config containing the registry URL
            call_args = mock_fetch.call_args[0][0]
            assert call_args["url"] == "http://example.com/feed"


class TestRedditAdapter:
    """Reddit adapter delegates to RedditCollector._fetch_subreddit."""

    def test_reddit_adapter_uses_config_subreddit(self):
        with patch("collectors.reddit.RedditCollector._fetch_subreddit") as mock_fetch:
            mock_fetch.return_value = [{"title": "Post", "source": "reddit", "source_id": "reddit_x",
                                         "url": "http://reddit.com/r/test/1", "content": "",
                                         "tags": [], "score": 0, "published_at": None, "author": ""}]
            from sources.adapters import _adapt_reddit
            articles = _adapt_reddit(_record("reddit:test", "reddit", {"subreddit": "TestSub"}))
            call_args = mock_fetch.call_args[0][0]
            assert call_args["subreddit"] == "TestSub"


class TestGitHubReleaseAdapter:
    """GitHub release adapter delegates to GitHubReleaseCollector._fetch_repo."""

    def test_github_release_uses_config_repo(self):
        with patch("collectors.github_release.GitHubReleaseCollector._fetch_repo") as mock_fetch:
            mock_fetch.return_value = [{"title": "v1.0", "source": "github_release", "source_id": "gr_1",
                                         "url": "http://github.com/x/y/releases/1", "content": "",
                                         "tags": [], "score": 0, "published_at": None, "author": ""}]
            from sources.adapters import _adapt_github_release
            articles = _adapt_github_release(_record("github_release:x-y", "github_release", {"repo": "x/y"}))
            call_args = mock_fetch.call_args[0][0]
            assert call_args["repo"] == "x/y"


class TestWebsiteMonitorAdapter:
    """Website monitor adapter dispatches based on config type."""

    def test_scrape_type(self):
        with patch("collectors.webpage_monitor.WebpageMonitorCollector._scrape_blog") as mock_scrape:
            mock_scrape.return_value = []
            from sources.adapters import _adapt_website_monitor
            _adapt_website_monitor(_record("website_monitor:test", "website_monitor",
                                           {"type": "scrape", "url": "http://example.com"}))
            mock_scrape.assert_called_once()


class TestSocialKOLAdapter:
    """Social KOL adapter delegates to SocialKolCollector."""

    def test_social_kol_calls_collector(self):
        with patch("collectors.social_kol.SocialKolCollector.collect") as mock_collect:
            mock_collect.return_value = []
            from sources.adapters import _adapt_social_kol
            _adapt_social_kol(_record("social_kol:curated-stream", "social_kol",
                                       {"handles": ["sama", "karpathy"]}))
            mock_collect.assert_called_once()

    def test_social_kol_filters_to_configured_handles(self):
        """Only articles from registry-configured handles pass through."""
        with patch("collectors.social_kol.SocialKolCollector.collect") as mock_collect:
            mock_collect.return_value = [
                {"author": "sama", "title": "Allowed", "source": "social_kol", "source_id": "cf_1",
                 "url": "http://x.com/1", "content": "", "tags": [], "score": 0, "published_at": None},
                {"author": "elonmusk", "title": "Not configured", "source": "social_kol", "source_id": "cf_2",
                 "url": "http://x.com/2", "content": "", "tags": [], "score": 0, "published_at": None},
                {"author": "", "title": "Blank author", "source": "social_kol", "source_id": "cf_3",
                 "url": "http://x.com/3", "content": "", "tags": [], "score": 0, "published_at": None},
                {"author": None, "title": "None author", "source": "social_kol", "source_id": "cf_4",
                 "url": "http://x.com/4", "content": "", "tags": [], "score": 0, "published_at": None},
            ]
            from sources.adapters import _adapt_social_kol
            articles = _adapt_social_kol(_record("social_kol:curated-stream", "social_kol",
                                                  {"handles": ["sama", "karpathy"]}))
            # Only "sama" should pass; elonmusk is not configured, blank/None authors are excluded
            assert len(articles) == 1
            assert articles[0]["author"] == "sama"


class TestAdapterArticleShape:
    """All adapters return article dicts with required fields."""

    def test_rss_article_has_source_field(self):
        with patch("collectors.rss.RSSCollector._fetch_feed") as mock_fetch:
            mock_fetch.return_value = [{"title": "T", "source": "rss", "source_id": "rss_x",
                                         "url": "http://example.com", "content": "c",
                                         "tags": [], "score": 0, "published_at": None, "author": "a"}]
            from sources.adapters import _adapt_rss
            articles = _adapt_rss(_record("rss:test", "rss", {"url": "http://example.com/feed", "name": "Test"}))
            assert len(articles) == 1
            assert "source" in articles[0]
            assert "title" in articles[0]


# --- Helpers ---

def _record(source_key: str, source_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal source record dict for adapter tests."""
    return {
        "source_key": source_key,
        "source_type": source_type,
        "display_name": source_key,
        "category": None,
        "config": config,
        "config_json": json.dumps(config),
    }
