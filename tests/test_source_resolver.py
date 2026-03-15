"""Tests for the source URL/reference resolver."""

import pytest

from sources.resolver import resolve_source


class TestResolveReddit:
    def test_subreddit_url(self):
        result = resolve_source("https://www.reddit.com/r/LocalLLaMA/")
        assert result["source_type"] == "reddit"
        assert result["config"]["subreddit"] == "LocalLLaMA"

    def test_subreddit_url_no_trailing_slash(self):
        result = resolve_source("https://reddit.com/r/MachineLearning")
        assert result["source_type"] == "reddit"
        assert result["config"]["subreddit"] == "MachineLearning"

    def test_old_reddit_url(self):
        result = resolve_source("https://old.reddit.com/r/ChatGPT/top/")
        assert result["source_type"] == "reddit"
        assert result["config"]["subreddit"] == "ChatGPT"

    def test_display_name(self):
        result = resolve_source("https://reddit.com/r/Anthropic")
        assert result["display_name"] == "r/Anthropic"


class TestResolveHackerNews:
    def test_hn_url(self):
        result = resolve_source("https://news.ycombinator.com/")
        assert result["source_type"] == "hackernews"

    def test_hn_item_url(self):
        result = resolve_source("https://news.ycombinator.com/item?id=12345")
        assert result["source_type"] == "hackernews"


class TestResolveRSS:
    def test_rss_xml_url(self):
        result = resolve_source("https://example.com/feed.xml")
        assert result["source_type"] == "rss"
        assert result["config"]["url"] == "https://example.com/feed.xml"

    def test_atom_url(self):
        result = resolve_source("https://example.com/atom.xml")
        assert result["source_type"] == "rss"

    def test_rss_path(self):
        result = resolve_source("https://example.com/rss")
        assert result["source_type"] == "rss"

    def test_feed_path(self):
        result = resolve_source("https://example.com/feed")
        assert result["source_type"] == "rss"

    def test_feed_with_substack(self):
        result = resolve_source("https://newsletter.example.com/feed")
        assert result["source_type"] == "rss"


class TestResolveGitHubTrending:
    def test_github_trending_url(self):
        result = resolve_source("https://github.com/trending")
        assert result["source_type"] == "github_trending"

    def test_github_trending_with_lang(self):
        result = resolve_source("https://github.com/trending/python")
        assert result["source_type"] == "github_trending"


class TestResolveGitHubRelease:
    def test_github_repo_releases(self):
        result = resolve_source("https://github.com/openai/codex/releases")
        assert result["source_type"] == "github_release"
        assert result["config"]["repo"] == "openai/codex"

    def test_github_repo_url_is_not_release(self):
        """Generic repo URLs should NOT be classified as github_release."""
        result = resolve_source("https://github.com/anthropics/claude-code")
        assert result["source_type"] == "website_monitor"
        assert "github.com" in result["config"]["url"]


class TestResolveWebsiteMonitor:
    def test_generic_webpage(self):
        result = resolve_source("https://claude.com/blog/")
        assert result["source_type"] == "website_monitor"
        assert result["config"]["url"] == "https://claude.com/blog/"

    def test_random_url_falls_through(self):
        result = resolve_source("https://example.com/some-page")
        assert result["source_type"] == "website_monitor"


class TestResolveReturnShape:
    """All resolve results have the required keys."""

    def test_required_keys(self):
        result = resolve_source("https://reddit.com/r/test")
        assert "source_type" in result
        assert "display_name" in result
        assert "config" in result
        assert isinstance(result["config"], dict)


class TestResolveEdgeCases:
    def test_empty_string(self):
        result = resolve_source("")
        assert result["source_type"] == "website_monitor"

    def test_plain_text_not_url(self):
        result = resolve_source("just some text")
        assert result["source_type"] == "website_monitor"
