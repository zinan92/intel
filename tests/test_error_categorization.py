"""Tests for sources.errors — error categorization, retryability, and CollectorResult."""

from __future__ import annotations

import json

import pytest
import requests
import requests.models

from sources.errors import (
    CollectorResult,
    ErrorCategory,
    categorize_error,
    is_retryable,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_error(status_code: int) -> requests.HTTPError:
    """Build an HTTPError with a specific status code."""
    resp = requests.models.Response()
    resp.status_code = status_code
    return requests.HTTPError(response=resp)


# ---------------------------------------------------------------------------
# ErrorCategory enum
# ---------------------------------------------------------------------------

class TestErrorCategory:
    def test_has_exactly_four_values(self) -> None:
        assert len(ErrorCategory) == 4

    def test_transient_value(self) -> None:
        assert ErrorCategory.TRANSIENT.value == "transient"

    def test_auth_value(self) -> None:
        assert ErrorCategory.AUTH.value == "auth"

    def test_parse_value(self) -> None:
        assert ErrorCategory.PARSE.value == "parse"

    def test_config_value(self) -> None:
        assert ErrorCategory.CONFIG.value == "config"


# ---------------------------------------------------------------------------
# categorize_error — transient
# ---------------------------------------------------------------------------

class TestCategorizeTransient:
    def test_connection_error(self) -> None:
        assert categorize_error(requests.ConnectionError()) == ErrorCategory.TRANSIENT

    def test_timeout(self) -> None:
        assert categorize_error(requests.Timeout()) == ErrorCategory.TRANSIENT

    def test_os_error(self) -> None:
        assert categorize_error(OSError("network down")) == ErrorCategory.TRANSIENT

    def test_http_429(self) -> None:
        assert categorize_error(_http_error(429)) == ErrorCategory.TRANSIENT

    def test_http_500(self) -> None:
        assert categorize_error(_http_error(500)) == ErrorCategory.TRANSIENT

    def test_http_502(self) -> None:
        assert categorize_error(_http_error(502)) == ErrorCategory.TRANSIENT

    def test_http_503(self) -> None:
        assert categorize_error(_http_error(503)) == ErrorCategory.TRANSIENT

    def test_http_error_no_response(self) -> None:
        """Pitfall 2: HTTPError with response=None should be transient."""
        assert categorize_error(requests.HTTPError(response=None)) == ErrorCategory.TRANSIENT


# ---------------------------------------------------------------------------
# categorize_error — auth
# ---------------------------------------------------------------------------

class TestCategorizeAuth:
    def test_http_401(self) -> None:
        assert categorize_error(_http_error(401)) == ErrorCategory.AUTH

    def test_http_403(self) -> None:
        assert categorize_error(_http_error(403)) == ErrorCategory.AUTH

    def test_http_400_xueqiu_cookie(self) -> None:
        """D-09: Xueqiu cookie expiry returns 400, classified as auth."""
        assert categorize_error(_http_error(400)) == ErrorCategory.AUTH


# ---------------------------------------------------------------------------
# categorize_error — parse
# ---------------------------------------------------------------------------

class TestCategorizeParse:
    def test_value_error(self) -> None:
        assert categorize_error(ValueError("bad data")) == ErrorCategory.PARSE

    def test_key_error(self) -> None:
        """Pitfall 1: KeyError in adapter layer = parse error."""
        assert categorize_error(KeyError("missing_field")) == ErrorCategory.PARSE

    def test_json_decode_error(self) -> None:
        exc = json.JSONDecodeError("Expecting value", "", 0)
        assert categorize_error(exc) == ErrorCategory.PARSE


# ---------------------------------------------------------------------------
# categorize_error — config
# ---------------------------------------------------------------------------

class TestCategorizeConfig:
    def test_import_error(self) -> None:
        assert categorize_error(ImportError("no module")) == ErrorCategory.CONFIG

    def test_file_not_found(self) -> None:
        assert categorize_error(FileNotFoundError("/path")) == ErrorCategory.CONFIG


# ---------------------------------------------------------------------------
# is_retryable
# ---------------------------------------------------------------------------

class TestIsRetryable:
    def test_transient_is_retryable(self) -> None:
        assert is_retryable(requests.ConnectionError()) is True

    def test_auth_not_retryable(self) -> None:
        assert is_retryable(_http_error(401)) is False

    def test_parse_not_retryable(self) -> None:
        assert is_retryable(ValueError("bad")) is False

    def test_config_not_retryable(self) -> None:
        assert is_retryable(ImportError("missing")) is False


# ---------------------------------------------------------------------------
# CollectorResult dataclass
# ---------------------------------------------------------------------------

class TestCollectorResult:
    def test_frozen(self) -> None:
        result = CollectorResult(
            source_type="rss",
            source_key="techcrunch",
            status="ok",
            articles_fetched=10,
            articles_saved=8,
            duration_ms=1500,
            error_message=None,
            error_category=None,
            retry_count=0,
        )
        with pytest.raises(AttributeError):
            result.status = "error"  # type: ignore[misc]

    def test_all_fields_present(self) -> None:
        result = CollectorResult(
            source_type="hackernews",
            source_key="hn_top",
            status="error",
            articles_fetched=0,
            articles_saved=0,
            duration_ms=250,
            error_message="Connection refused",
            error_category="transient",
            retry_count=3,
        )
        assert result.source_type == "hackernews"
        assert result.source_key == "hn_top"
        assert result.status == "error"
        assert result.articles_fetched == 0
        assert result.articles_saved == 0
        assert result.duration_ms == 250
        assert result.error_message == "Connection refused"
        assert result.error_category == "transient"
        assert result.retry_count == 3
