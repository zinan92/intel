"""Tests that the primary product UI hides source-layer implementation details.

The feed-first UI should not require source awareness to be useful.
Implementation-oriented names like 'clawfeed' must never appear in
user-facing contracts. Source health is available but rendered in
domain-neutral language (V2 type names, not tool names).
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    with patch("main.CollectorScheduler.start"), \
         patch("main.CollectorScheduler.shutdown"):
        from main import app
        with TestClient(app) as c:
            yield c


class TestFeedDoesNotRequireSourceAwareness:
    """The primary feed endpoint works without source knowledge."""

    def test_feed_returns_items_without_source_filter(self, client):
        resp = client.get("/api/ui/feed?min_relevance=1")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_feed_items_use_source_kind_not_raw_source(self, client):
        """Items should have source_kind (domain label) not just raw source."""
        resp = client.get("/api/ui/feed?min_relevance=1")
        for item in resp.json()["items"]:
            assert "source_kind" in item


class TestNoClawfeedInUserContracts:
    """'clawfeed' must not appear in any user-facing API response."""

    def test_feed_items_no_clawfeed(self, client):
        resp = client.get("/api/ui/feed?min_relevance=1&window=7d")
        for item in resp.json()["items"]:
            assert item.get("source") != "clawfeed", \
                "clawfeed must not appear as source in feed items"
            assert item.get("source_kind") != "clawfeed"

    def test_sources_list_no_clawfeed(self, client):
        resp = client.get("/api/ui/sources")
        names = {s["name"] for s in resp.json()}
        assert "clawfeed" not in names

    def test_source_health_no_clawfeed(self, client):
        resp = client.get("/api/ui/feed")
        health = resp.json()["context"]["source_health"]
        health_names = {h["source"] for h in health}
        assert "clawfeed" not in health_names

    def test_health_endpoint_no_clawfeed(self, client):
        resp = client.get("/api/health")
        sources = resp.json()["sources"]
        assert "clawfeed" not in sources

    def test_topics_no_clawfeed(self, client):
        resp = client.get("/api/ui/topics")
        assert resp.status_code == 200
        # Topic data itself shouldn't reference clawfeed


class TestNoLegacyNamesInSourceEndpoints:
    """V2 source endpoints should use normalized names only."""

    def test_sources_list_uses_v2_names(self, client):
        resp = client.get("/api/ui/sources")
        names = {s["name"] for s in resp.json()}
        # No legacy names
        assert "clawfeed" not in names
        assert "github" not in names  # should be github_trending
        assert "webpage_monitor" not in names  # should be website_monitor

    def test_health_uses_v2_names(self, client):
        resp = client.get("/api/health")
        sources = resp.json()["sources"]
        assert "clawfeed" not in sources
        assert "github" not in sources
        assert "webpage_monitor" not in sources


class TestSourceHealthIsDomainNeutral:
    """Source health in the feed context uses domain-oriented labels."""

    def test_source_health_uses_v2_type_names(self, client):
        resp = client.get("/api/ui/feed")
        health = resp.json()["context"]["source_health"]
        health_names = {h["source"] for h in health}
        # Should use V2 names
        for legacy in ["clawfeed", "github", "webpage_monitor"]:
            assert legacy not in health_names, f"Legacy name {legacy} in source_health"

    def test_source_health_entries_have_status(self, client):
        resp = client.get("/api/ui/feed")
        health = resp.json()["context"]["source_health"]
        for h in health:
            assert "status" in h
            assert h["status"] in ("ok", "stale", "no_data", "degraded")
