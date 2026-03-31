"""Tests for retry integration in sources/adapters.py.

Verifies that collect_from_source retries transient errors (ConnectionError,
Timeout, HTTPError 429/500/502/503) up to 3 attempts, does NOT retry
non-transient errors (HTTPError 401, ValueError), and returns
(articles, CollectorResult) tuples with correct metadata.
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from sources.adapters import collect_from_source
from sources.errors import CollectorResult


def _record(source_key: str, source_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal source record dict for tests."""
    return {
        "source_key": source_key,
        "source_type": source_type,
        "display_name": source_key,
        "category": None,
        "config": config,
        "config_json": json.dumps(config),
    }


def _make_http_error(status_code: int) -> requests.HTTPError:
    """Create an HTTPError with a mocked response carrying the given status code."""
    response = requests.models.Response()
    response.status_code = status_code
    return requests.HTTPError(response=response)


class TestTransientRetry:
    """Transient errors are retried up to 3 attempts."""

    @patch("tenacity.nap.time.sleep")
    def test_connection_error_retried_then_succeeds(self, mock_sleep):
        """ConnectionError retries twice, then succeeds on 3rd call."""
        call_count = 0

        def flaky_adapter(record):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.ConnectionError("connection refused")
            return [{"title": "Test Article"}]

        with patch("sources.adapters.get_adapter", return_value=flaky_adapter):
            record = _record("test:flaky", "test", {})
            articles, result = collect_from_source(record)

        assert len(articles) == 1
        assert articles[0]["title"] == "Test Article"
        assert result.status == "ok"
        assert result.retry_count == 2
        assert result.articles_fetched == 1

    @patch("tenacity.nap.time.sleep")
    def test_timeout_retried_then_succeeds(self, mock_sleep):
        """Timeout retries twice, then succeeds on 3rd call."""
        call_count = 0

        def flaky_adapter(record):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise requests.Timeout("request timed out")
            return [{"title": "OK"}]

        with patch("sources.adapters.get_adapter", return_value=flaky_adapter):
            record = _record("test:timeout", "test", {})
            articles, result = collect_from_source(record)

        assert len(articles) == 1
        assert result.status == "ok"
        assert result.retry_count == 2

    @patch("tenacity.nap.time.sleep")
    def test_http_429_retried_then_succeeds(self, mock_sleep):
        """HTTP 429 (rate limit) is retried."""
        call_count = 0

        def flaky_adapter(record):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _make_http_error(429)
            return [{"title": "Rate Limit OK"}]

        with patch("sources.adapters.get_adapter", return_value=flaky_adapter):
            record = _record("test:ratelimit", "test", {})
            articles, result = collect_from_source(record)

        assert len(articles) == 1
        assert result.status == "ok"
        assert result.retry_count == 2

    @patch("tenacity.nap.time.sleep")
    def test_transient_exhaustion_returns_error(self, mock_sleep):
        """All 3 attempts fail with ConnectionError -> error result."""
        def always_fail(record):
            raise requests.ConnectionError("always down")

        with patch("sources.adapters.get_adapter", return_value=always_fail):
            record = _record("test:down", "test", {})
            articles, result = collect_from_source(record)

        assert articles == []
        assert result.status == "error"
        assert result.error_category == "transient"
        assert result.retry_count == 2
        assert "always down" in result.error_message


class TestNonTransientNoRetry:
    """Non-transient errors fail immediately without retry."""

    @patch("tenacity.nap.time.sleep")
    def test_http_401_no_retry(self, mock_sleep):
        """HTTP 401 (auth) fails immediately."""
        call_count = 0

        def auth_fail(record):
            nonlocal call_count
            call_count += 1
            raise _make_http_error(401)

        with patch("sources.adapters.get_adapter", return_value=auth_fail):
            record = _record("test:auth", "test", {})
            articles, result = collect_from_source(record)

        assert articles == []
        assert result.status == "error"
        assert result.error_category == "auth"
        assert result.retry_count == 0
        assert call_count == 1  # only called once, no retry

    @patch("tenacity.nap.time.sleep")
    def test_value_error_no_retry(self, mock_sleep):
        """ValueError (parse) fails immediately."""
        call_count = 0

        def parse_fail(record):
            nonlocal call_count
            call_count += 1
            raise ValueError("invalid data format")

        with patch("sources.adapters.get_adapter", return_value=parse_fail):
            record = _record("test:parse", "test", {})
            articles, result = collect_from_source(record)

        assert articles == []
        assert result.status == "error"
        assert result.error_category == "parse"
        assert result.retry_count == 0
        assert call_count == 1


class TestSuccessPath:
    """Successful collection returns correct metadata."""

    @patch("tenacity.nap.time.sleep")
    def test_success_returns_articles_and_result(self, mock_sleep):
        """Successful adapter call returns articles and CollectorResult."""
        def good_adapter(record):
            return [{"title": "Article 1"}, {"title": "Article 2"}]

        with patch("sources.adapters.get_adapter", return_value=good_adapter):
            record = _record("test:good", "test", {})
            articles, result = collect_from_source(record)

        assert len(articles) == 2
        assert result.status == "ok"
        assert result.articles_fetched == 2
        assert result.articles_saved == 0  # saved is filled by scheduler
        assert result.duration_ms >= 0
        assert result.retry_count == 0
        assert result.error_message is None
        assert result.error_category is None
        assert result.source_type == "test"
        assert result.source_key == "test:good"


class TestUnknownAdapter:
    """Unknown source type returns config error."""

    def test_unknown_adapter_returns_config_error(self):
        record = _record("unknown:x", "nonexistent_type", {})
        articles, result = collect_from_source(record)

        assert articles == []
        assert result.status == "error"
        assert result.error_category == "config"
        assert result.retry_count == 0
