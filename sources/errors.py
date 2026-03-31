"""Error categorization and collector result types for reliability instrumentation.

Provides:
- ErrorCategory enum (transient, auth, parse, config)
- categorize_error() to classify exceptions
- is_retryable() predicate for tenacity retry decisions
- CollectorResult frozen dataclass for recording execution outcomes
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

import requests


class ErrorCategory(str, Enum):
    """Four-way classification of collector errors (D-10)."""

    TRANSIENT = "transient"
    AUTH = "auth"
    PARSE = "parse"
    CONFIG = "config"


_TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503})
_AUTH_HTTP_CODES = frozenset({400, 401, 403})


def categorize_error(exc: Exception) -> ErrorCategory:
    """Classify an exception into one of four error categories.

    Classification rules (per D-05, D-06, D-09, D-10):
    - ConnectionError, Timeout, OSError -> TRANSIENT
    - HTTPError with 429/500/502/503 -> TRANSIENT
    - HTTPError with 400/401/403 -> AUTH (D-09: 400 = Xueqiu cookie expiry)
    - HTTPError with response=None -> TRANSIENT (Pitfall 2)
    - ValueError, KeyError, TypeError, JSONDecodeError -> PARSE
    - ImportError, FileNotFoundError -> CONFIG
    - Unknown exceptions -> TRANSIENT (fail-open for retry)
    """
    # Network-level errors: always transient
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return ErrorCategory.TRANSIENT

    # HTTP errors: classify by status code
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        if response is None:
            return ErrorCategory.TRANSIENT
        code = response.status_code
        if code in _TRANSIENT_HTTP_CODES:
            return ErrorCategory.TRANSIENT
        if code in _AUTH_HTTP_CODES:
            return ErrorCategory.AUTH
        return ErrorCategory.TRANSIENT

    # Configuration / environment errors (check before OSError since
    # FileNotFoundError is a subclass of OSError)
    if isinstance(exc, (ImportError, FileNotFoundError)):
        return ErrorCategory.CONFIG

    # OS-level network errors (socket errors etc.)
    if isinstance(exc, OSError):
        return ErrorCategory.TRANSIENT

    # Parse / data errors
    if isinstance(exc, (ValueError, KeyError, TypeError, json.JSONDecodeError)):
        return ErrorCategory.PARSE

    # Unknown: default to transient (fail-open for retry)
    return ErrorCategory.TRANSIENT


def is_retryable(exc: Exception) -> bool:
    """Return True if the exception should be retried (transient only)."""
    return categorize_error(exc) == ErrorCategory.TRANSIENT


@dataclass(frozen=True)
class CollectorResult:
    """Immutable record of a single collector execution attempt (D-03/D-12).

    This is the richer version for DB persistence. The simpler
    scheduler.CollectorResult remains for backward compat with _last_results.
    """

    source_type: str
    source_key: str
    status: str  # "ok" or "error"
    articles_fetched: int
    articles_saved: int
    duration_ms: int
    error_message: str | None
    error_category: str | None
    retry_count: int
