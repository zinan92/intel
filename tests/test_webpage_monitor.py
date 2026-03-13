"""Tests for WebpageMonitorCollector — state file, scrape, and GitHub commits."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from collectors.webpage_monitor import WebpageMonitorCollector, _load_state, _save_state


BLOG_MONITOR = {
    "name": "Anthropic Claude Blog",
    "type": "scrape",
    "url": "https://claude.com/blog/",
    "category": "llm",
}

COMMITS_MONITOR = {
    "name": "OpenClaw Docs",
    "type": "github_commits",
    "repo": "openclaw/openclaw",
    "path": "docs/",
    "category": "ai-agent",
}

SAMPLE_BLOG_HTML = """
<html><body>
<a href="/blog/new-feature">New Feature Announcement</a>
<a href="/blog/another-post">Another Post</a>
<a href="/blog/">Index link</a>
<a href="https://other.com/page">External link</a>
</body></html>
"""

SAMPLE_COMMITS = [
    {
        "sha": "abc123def456",
        "html_url": "https://github.com/openclaw/openclaw/commit/abc123def456",
        "commit": {"message": "docs: update getting started", "author": {"name": "devuser"}},
        "author": {"login": "devuser"},
    },
    {
        "sha": "111222333444",
        "html_url": "https://github.com/openclaw/openclaw/commit/111222333444",
        "commit": {"message": "docs: fix typo", "author": {"name": "devuser"}},
        "author": {"login": "devuser"},
    },
]


def _make_resp(text_or_json, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    if isinstance(text_or_json, str):
        resp.text = text_or_json
        resp.json.return_value = None
    else:
        resp.text = json.dumps(text_or_json)
        resp.json.return_value = text_or_json
    return resp


# --- State file tests ---

def test_load_state_returns_empty_when_missing(tmp_path):
    state_path = tmp_path / "state.json"
    state = _load_state(state_path)
    assert state == {"seen_urls": {}, "last_seen_commit": {}}


def test_save_and_load_state(tmp_path):
    state_path = tmp_path / "state.json"
    original = {"seen_urls": {"Blog": ["https://example.com/post"]}, "last_seen_commit": {}}
    _save_state(state_path, original)
    loaded = _load_state(state_path)
    assert loaded == original


# --- Blog scrape tests ---

def test_scrape_returns_new_urls(tmp_path):
    state_path = tmp_path / "state.json"
    collector = WebpageMonitorCollector(state_path=state_path)
    resp = _make_resp(SAMPLE_BLOG_HTML)

    with patch("collectors.webpage_monitor.requests.get", return_value=resp), \
         patch("collectors.webpage_monitor.config.WEBPAGE_MONITORS", [BLOG_MONITOR]):
        result = collector.collect()

    urls = [a["url"] for a in result]
    assert "https://claude.com/blog/new-feature" in urls
    assert "https://claude.com/blog/another-post" in urls
    # Index and external links excluded
    assert "https://claude.com/blog/" not in urls
    assert "https://other.com/page" not in urls


def test_scrape_skips_already_seen(tmp_path):
    state_path = tmp_path / "state.json"
    # Pre-seed state with one URL
    _save_state(state_path, {
        "seen_urls": {"Anthropic Claude Blog": ["https://claude.com/blog/new-feature"]},
        "last_seen_commit": {},
    })
    collector = WebpageMonitorCollector(state_path=state_path)
    resp = _make_resp(SAMPLE_BLOG_HTML)

    with patch("collectors.webpage_monitor.requests.get", return_value=resp), \
         patch("collectors.webpage_monitor.config.WEBPAGE_MONITORS", [BLOG_MONITOR]):
        result = collector.collect()

    urls = [a["url"] for a in result]
    assert "https://claude.com/blog/new-feature" not in urls
    assert "https://claude.com/blog/another-post" in urls


def test_scrape_state_persisted_after_run(tmp_path):
    state_path = tmp_path / "state.json"
    collector = WebpageMonitorCollector(state_path=state_path)
    resp = _make_resp(SAMPLE_BLOG_HTML)

    with patch("collectors.webpage_monitor.requests.get", return_value=resp), \
         patch("collectors.webpage_monitor.config.WEBPAGE_MONITORS", [BLOG_MONITOR]):
        collector.collect()

    state = _load_state(state_path)
    assert "Anthropic Claude Blog" in state["seen_urls"]
    assert len(state["seen_urls"]["Anthropic Claude Blog"]) >= 2


def test_scrape_failure_returns_empty(tmp_path):
    state_path = tmp_path / "state.json"
    collector = WebpageMonitorCollector(state_path=state_path)

    with patch("collectors.webpage_monitor.requests.get", side_effect=Exception("timeout")), \
         patch("collectors.webpage_monitor.config.WEBPAGE_MONITORS", [BLOG_MONITOR]):
        result = collector.collect()

    assert result == []


# --- GitHub commits tests ---

def test_commits_returns_new_entries(tmp_path):
    state_path = tmp_path / "state.json"
    collector = WebpageMonitorCollector(state_path=state_path)
    resp = _make_resp(SAMPLE_COMMITS)

    with patch("collectors.webpage_monitor.requests.get", return_value=resp), \
         patch("collectors.webpage_monitor.config.WEBPAGE_MONITORS", [COMMITS_MONITOR]), \
         patch("collectors.webpage_monitor.config.GITHUB_TOKEN", ""):
        result = collector.collect()

    assert len(result) == 2
    assert result[0]["source"] == "webpage_monitor"
    assert result[0]["title"].startswith("OpenClaw Docs:")


def test_commits_only_new_after_last_seen(tmp_path):
    state_path = tmp_path / "state.json"
    # Pre-seed last_seen to the second commit SHA
    _save_state(state_path, {
        "seen_urls": {},
        "last_seen_commit": {"openclaw/openclaw:docs/": "abc123def456"},
    })
    collector = WebpageMonitorCollector(state_path=state_path)
    resp = _make_resp(SAMPLE_COMMITS)

    with patch("collectors.webpage_monitor.requests.get", return_value=resp), \
         patch("collectors.webpage_monitor.config.WEBPAGE_MONITORS", [COMMITS_MONITOR]), \
         patch("collectors.webpage_monitor.config.GITHUB_TOKEN", ""):
        result = collector.collect()

    # abc123def456 is last_seen, so only entries BEFORE it — none here since it's first
    assert len(result) == 0


def test_commits_state_updated_with_newest_sha(tmp_path):
    state_path = tmp_path / "state.json"
    collector = WebpageMonitorCollector(state_path=state_path)
    resp = _make_resp(SAMPLE_COMMITS)

    with patch("collectors.webpage_monitor.requests.get", return_value=resp), \
         patch("collectors.webpage_monitor.config.WEBPAGE_MONITORS", [COMMITS_MONITOR]), \
         patch("collectors.webpage_monitor.config.GITHUB_TOKEN", ""):
        collector.collect()

    state = _load_state(state_path)
    assert state["last_seen_commit"]["openclaw/openclaw:docs/"] == "abc123def456"


def test_source_id_format():
    state = {"seen_urls": {}, "last_seen_commit": {}}
    collector = WebpageMonitorCollector.__new__(WebpageMonitorCollector)
    resp = _make_resp(SAMPLE_COMMITS)

    with patch("collectors.webpage_monitor.requests.get", return_value=resp), \
         patch("collectors.webpage_monitor.config.GITHUB_TOKEN", ""):
        articles = collector._monitor_github_commits(COMMITS_MONITOR, state)

    assert articles[0]["source_id"] == "webpage_commit_abc123def456"
