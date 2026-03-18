"""Tests for quant bridge price snapshot fetcher."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_get_price_snapshot_success():
    from bridge.quant import get_price_snapshot

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "price_at_event": 142.5,
        "change_1d": 3.2,
        "change_3d": 5.1,
        "change_5d": 4.8,
    }

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(get_price_snapshot("NVDA", datetime(2026, 3, 18)))
        assert result is not None
        assert result["price_at_event"] == 142.5
        assert result["change_1d"] == 3.2


def test_get_price_snapshot_timeout():
    from bridge.quant import get_price_snapshot
    import httpx

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client_cls.return_value = mock_client

        result = asyncio.run(get_price_snapshot("NVDA", datetime(2026, 3, 18)))
        assert result is None


def test_get_price_snapshot_404():
    from bridge.quant import get_price_snapshot

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(get_price_snapshot("FAKE", datetime(2026, 3, 18)))
        assert result is None


def test_get_price_impacts_parallel():
    from bridge.quant import get_price_impacts

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "price_at_event": 100.0,
        "change_1d": 1.0,
        "change_3d": 2.0,
        "change_5d": 3.0,
    }

    with patch("bridge.quant.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = asyncio.run(
            get_price_impacts(["NVDA", "AAPL"], datetime(2026, 3, 18))
        )
        assert len(result) == 2
        assert result[0]["ticker"] == "NVDA"
        assert result[1]["ticker"] == "AAPL"
