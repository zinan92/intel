"""Tests for SocialKolCollector — CLI-present and CLI-missing behavior."""
import json
from unittest.mock import MagicMock, patch

import pytest
from collectors.social_kol import SocialKolCollector


SAMPLE_ITEMS = [
    {
        "id": "abc123",
        "headline": "Sam Altman on AGI timelines",
        "summary": "In a recent post, Altman discusses...",
        "handle": "sama",
        "tweet_url": "https://x.com/sama/status/123",
    },
    {
        "title": "Karpathy on LLMs",
        "body": "Andrej explains neural nets...",
        "author": "karpathy",
        "url": "https://x.com/karpathy/status/456",
    },
    # Item without id — should use URL hash
    {
        "summary": "Something interesting",
        "handle": "rowancheung",
        "url": "https://x.com/rowancheung/status/789",
    },
]


def _make_collector_with_cli():
    with patch("shutil.which", return_value="/usr/local/bin/clawfeed"):
        c = SocialKolCollector()
    return c


def _make_collector_no_cli():
    with patch("shutil.which", return_value=None):
        c = SocialKolCollector()
    return c


def test_cli_missing_returns_empty():
    c = _make_collector_no_cli()
    result = c.collect()
    assert result == []


def test_cli_missing_logs_warning(caplog):
    import logging
    c = _make_collector_no_cli()
    with caplog.at_level(logging.WARNING, logger="collectors.social_kol"):
        c.collect()
    assert any("clawfeed CLI not available" in r.message for r in caplog.records)


def test_cli_present_returns_list():
    c = _make_collector_with_cli()
    output = json.dumps(SAMPLE_ITEMS)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = output.encode()
    mock_result.stderr = b""
    with patch("subprocess.run", return_value=mock_result):
        result = c.collect()
    assert isinstance(result, list)
    assert len(result) == 3


def test_source_id_uses_id_field():
    c = _make_collector_with_cli()
    output = json.dumps([SAMPLE_ITEMS[0]])
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = output.encode()
    mock_result.stderr = b""
    with patch("subprocess.run", return_value=mock_result):
        result = c.collect()
    assert result[0]["source_id"] == "social_kol_abc123"


def test_source_id_uses_url_hash_when_no_id():
    c = _make_collector_with_cli()
    item = {"summary": "content", "handle": "user", "url": "https://x.com/user/status/999"}
    output = json.dumps([item])
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = output.encode()
    mock_result.stderr = b""
    with patch("subprocess.run", return_value=mock_result):
        r1 = c.collect()

    with patch("subprocess.run", return_value=mock_result):
        r2 = c.collect()

    assert r1[0]["source_id"] == r2[0]["source_id"]
    assert r1[0]["source_id"].startswith("social_kol_")


def test_item_without_content_and_title_skipped():
    c = _make_collector_with_cli()
    bad_item = {"handle": "someone", "url": "https://x.com/someone/status/0"}
    output = json.dumps([bad_item])
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = output.encode()
    mock_result.stderr = b""
    with patch("subprocess.run", return_value=mock_result):
        result = c.collect()
    assert result == []


def test_mapping_fields():
    c = _make_collector_with_cli()
    output = json.dumps([SAMPLE_ITEMS[0]])
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = output.encode()
    mock_result.stderr = b""
    with patch("subprocess.run", return_value=mock_result):
        result = c.collect()
    a = result[0]
    assert a["source"] == "social_kol"
    assert a["title"] == "Sam Altman on AGI timelines"
    assert a["content"] == "In a recent post, Altman discusses..."
    assert a["author"] == "sama"
    assert a["url"] == "https://x.com/sama/status/123"


def test_cli_nonzero_exit_returns_empty():
    c = _make_collector_with_cli()
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = b""
    mock_result.stderr = b"error"
    with patch("subprocess.run", return_value=mock_result):
        result = c.collect()
    assert result == []
