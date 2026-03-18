"""Tests for ticker extraction from article text."""
import pytest


def test_extract_cashtag():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("Check out $NVDA and $AAPL today", "Great earnings")
    assert "NVDA" in tickers
    assert "AAPL" in tickers


def test_extract_company_name():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("NVIDIA reports record revenue", "")
    assert "NVDA" in tickers


def test_extract_chinese_company_name():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("英伟达财报超预期", "")
    assert "NVDA" in tickers


def test_extract_case_insensitive():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("nvidia beats expectations", "")
    assert "NVDA" in tickers


def test_extract_deduplicates():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("$NVDA NVIDIA 英伟达", "NVIDIA again")
    assert tickers.count("NVDA") == 1


def test_extract_no_tickers():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("General news about nothing", "Some content")
    assert tickers == []


def test_extract_from_yahoo_source():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("Gold prices rise", "", source_tickers=["GC=F", "GLD"])
    assert "GC=F" in tickers
    assert "GLD" in tickers


def test_title_and_content_both_scanned():
    from tagging.tickers import extract_tickers
    tickers = extract_tickers("Market update", "$TSLA is up 5%")
    assert "TSLA" in tickers
