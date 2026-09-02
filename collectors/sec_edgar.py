"""Official SEC EDGAR watchlist collector for the realtime lane."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any

import requests

from sources.errors import SourceBlockedError, SourceConfigurationError

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
_REQUEST_LOCK = Lock()
_LAST_REQUEST_AT: float | None = None
_MIN_REQUEST_GAP_SECONDS = 0.11


def _user_agent() -> str:
    value = os.getenv("SEC_EDGAR_USER_AGENT", "").strip()
    if not value:
        raise SourceConfigurationError("SEC_EDGAR_USER_AGENT is required")
    return value


def _headers() -> dict[str, str]:
    return {
        "User-Agent": _user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }


def _get_json(url: str) -> Any:
    """Fetch one official SEC JSON document within fair-access limits."""
    global _LAST_REQUEST_AT
    with _REQUEST_LOCK:
        now = time.monotonic()
        if _LAST_REQUEST_AT is not None:
            remaining = _MIN_REQUEST_GAP_SECONDS - (now - _LAST_REQUEST_AT)
            if remaining > 0:
                time.sleep(remaining)
                now = time.monotonic()
        _LAST_REQUEST_AT = now
        response = requests.get(url, headers=_headers(), timeout=15)
    if response.status_code in {403, 429, 451}:
        raise SourceBlockedError(f"sec_edgar provider blocked HTTP {response.status_code}")
    response.raise_for_status()
    return response.json()


def _parse_timestamp(value: Any, fallback_date: Any) -> datetime | None:
    raw = str(value or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
                timezone.utc
            ).replace(tzinfo=None)
        except ValueError:
            return None
    raw_date = str(fallback_date or "").strip()
    if not raw_date:
        return None
    try:
        return datetime.strptime(raw_date, "%Y-%m-%d")
    except ValueError:
        return None


def _company_index() -> dict[str, tuple[int, str]]:
    payload = _get_json(COMPANY_TICKERS_URL)
    if not isinstance(payload, dict):
        raise TypeError("SEC company_tickers payload must be an object")
    result: dict[str, tuple[int, str]] = {}
    for row in payload.values():
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        title = str(row.get("title") or "").strip()
        try:
            cik = int(row.get("cik_str"))
        except (TypeError, ValueError):
            continue
        if ticker:
            if ticker in result and result[ticker][0] != cik:
                raise SourceConfigurationError(
                    f"SEC ticker mapping is ambiguous: {ticker}"
                )
            result[ticker] = (cik, title)
    return result


def _recent_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    recent = payload.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict):
        raise TypeError("SEC submissions filings.recent must be an object")
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        raise TypeError("SEC submissions accessionNumber must be a list")
    rows: list[dict[str, Any]] = []
    for index in range(len(accessions)):
        rows.append({
            key: value[index] if isinstance(value, list) and index < len(value) else None
            for key, value in recent.items()
        })
    return rows


def fetch_sec_edgar_filings(
    *,
    tickers: list[str],
    forms: list[str],
    cik_map: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Resolve the watchlist through SEC metadata and return approved filings."""
    company_index = _company_index()
    approved_forms = {form.strip().upper() for form in forms if form.strip()}
    normalized: list[dict[str, Any]] = []
    for raw_ticker in tickers:
        ticker = raw_ticker.strip().upper()
        if ticker not in company_index:
            raise SourceConfigurationError(f"SEC ticker mapping not found: {ticker}")
        cik, indexed_title = company_index[ticker]
        if cik_map is not None:
            try:
                pinned_cik = int(cik_map[ticker])
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceConfigurationError(
                    f"SEC CIK pin missing or invalid: {ticker}"
                ) from exc
            if pinned_cik != cik:
                raise SourceConfigurationError(
                    f"SEC CIK pin mismatch for {ticker}: expected {pinned_cik}, official {cik}"
                )
        url = SUBMISSIONS_URL.format(cik=cik)
        payload = _get_json(url)
        if not isinstance(payload, dict):
            raise TypeError(f"SEC submissions payload must be an object: {ticker}")
        company = str(payload.get("name") or indexed_title or ticker).strip()
        for row in _recent_rows(payload):
            form = str(row.get("form") or "").strip().upper()
            if form not in approved_forms:
                continue
            accession = str(row.get("accessionNumber") or "").strip()
            document = str(row.get("primaryDocument") or "").strip()
            if not accession or not document:
                continue
            published_at = _parse_timestamp(
                row.get("acceptanceDateTime"), row.get("filingDate")
            )
            description = str(row.get("primaryDocDescription") or form).strip()
            report_date = str(row.get("reportDate") or row.get("filingDate") or "").strip()
            items = str(row.get("items") or "").strip()
            content = f"{company} filed {form} for {report_date}."
            if items:
                content += f" Items: {items}."
            normalized.append({
                "source": "sec_edgar",
                "source_id": f"sec_edgar:{accession}",
                "author": company,
                "title": f"{ticker} {form} — {description}",
                "content": content,
                "url": ARCHIVES_URL.format(
                    cik=cik,
                    accession=accession.replace("-", ""),
                    document=document,
                ),
                "tags": ["sec-filing", form.lower()],
                "tickers": [ticker],
                "score": 0,
                "published_at": published_at,
                "collection_lane": "realtime",
                "source_authority": "official",
                "corroboration_state": "primary_source",
                "pin_eligibility": "eligible_if_high_impact",
                "_timestamp_status": "valid" if published_at else "missing",
            })
    return normalized
