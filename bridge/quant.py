"""Async bridge to quant-data-pipeline for price impact data."""
import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx

from config import QUANT_API_BASE_URL

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 3.0


async def get_price_snapshot(
    ticker: str,
    event_date: datetime,
) -> dict[str, Any] | None:
    url = f"{QUANT_API_BASE_URL}/api/price/{ticker}"
    params = {"date": event_date.strftime("%Y-%m-%d")}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("Quant API returned %d for %s on %s", resp.status_code, ticker, event_date.date())
                return None
            return resp.json()
    except httpx.TimeoutException:
        logger.warning("Quant API timeout for %s", ticker)
        return None
    except Exception:
        logger.warning("Quant API error for %s", ticker, exc_info=True)
        return None


async def get_price_impacts(
    tickers: list[str],
    event_date: datetime,
) -> list[dict[str, Any]]:
    tasks = [get_price_snapshot(t, event_date) for t in tickers]
    results = await asyncio.gather(*tasks)

    impacts = []
    for ticker, result in zip(tickers, results):
        if result is not None:
            impacts.append({"ticker": ticker, **result})

    return impacts
