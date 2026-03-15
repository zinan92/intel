"""Tests for source name canonicalization at write time.

Verifies that collectors emit canonical V2 source names, not legacy names.
"""

import pytest
from unittest.mock import patch, MagicMock

from collectors.social_kol import SocialKolCollector
from collectors.github_trending import GitHubTrendingCollector
from collectors.webpage_monitor import WebpageMonitorCollector


class TestCollectorSourceAttributes:
    """Collector class `source` attributes must use canonical V2 names."""

    def test_clawfeed_collector_uses_social_kol(self):
        assert SocialKolCollector.source == "social_kol"

    def test_github_trending_collector_uses_github_trending(self):
        assert GitHubTrendingCollector.source == "github_trending"

    def test_webpage_monitor_collector_uses_website_monitor(self):
        assert WebpageMonitorCollector.source == "website_monitor"


class TestCollectorArticleDicts:
    """Articles returned by collectors must carry canonical source names."""

    @patch.object(SocialKolCollector, "_fetch_via_cli")
    def test_social_kol_articles_have_canonical_source(self, mock_fetch):
        mock_fetch.return_value = [
            {"author": "@test", "title": "Test", "content": "body",
             "url": "https://x.com/test/1", "source": "social_kol",
             "source_id": "social_kol:test1"}
        ]
        collector = SocialKolCollector()
        articles = collector.collect()
        for a in articles:
            assert a["source"] == "social_kol", f"Expected 'social_kol', got {a['source']!r}"

    @patch.object(GitHubTrendingCollector, "_get_readme_content", return_value="")
    @patch.object(GitHubTrendingCollector, "_search_recent_repos")
    def test_github_trending_articles_have_canonical_source(self, mock_search, _mock_readme):
        mock_search.return_value = [
            {
                "full_name": "test/ai-repo",
                "name": "ai-repo",
                "description": "An AI project",
                "html_url": "https://github.com/test/ai-repo",
                "stargazers_count": 500,
                "forks_count": 50,
                "language": "Python",
                "topics": ["ai"],
                "owner": {"login": "test"},
                "created_at": "2026-03-15T00:00:00Z",
            }
        ]
        collector = GitHubTrendingCollector()
        articles = collector.collect()
        assert len(articles) > 0
        for a in articles:
            assert a["source"] == "github_trending", f"Expected 'github_trending', got {a['source']!r}"


class TestNoLegacySourceNames:
    """No collector should use legacy source names as class attributes."""

    LEGACY_NAMES = {"clawfeed", "github", "webpage_monitor"}

    def test_no_collector_uses_legacy_names(self):
        from collectors.base import BaseCollector
        import collectors.social_kol
        import collectors.github_trending
        import collectors.webpage_monitor
        import collectors.hackernews
        import collectors.rss
        import collectors.reddit
        import collectors.github_release
        import collectors.xueqiu
        import collectors.yahoo_finance
        import collectors.google_news

        modules = [
            collectors.social_kol,
            collectors.github_trending,
            collectors.webpage_monitor,
            collectors.hackernews,
            collectors.rss,
            collectors.reddit,
            collectors.github_release,
            collectors.xueqiu,
            collectors.yahoo_finance,
            collectors.google_news,
        ]

        for mod in modules:
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if isinstance(obj, type) and issubclass(obj, BaseCollector) and obj is not BaseCollector:
                    assert obj.source not in self.LEGACY_NAMES, (
                        f"{obj.__name__}.source = {obj.source!r} is a legacy name"
                    )
