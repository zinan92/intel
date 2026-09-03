"""Deterministic exposure matching for the approved realtime asset universe."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable


EXPOSURE_UNIVERSE_VERSION = "macro-assets-v3"

# Keep this order stable.  It is the same 16-asset universe used by the
# Human K-line Review / Daily K-line products; it is deliberately local here so
# realtime News Liquid does not import another product's runtime.
APPROVED_ASSET_KEYS = (
    "dxy", "sp500", "nasdaq", "us_dividend", "vix",
    "bitcoin", "ethereum", "hype",
    "shanghai", "star50", "china_dividend", "nikkei", "kospi",
    "wti", "gold", "silver",
)


@dataclass(frozen=True)
class ExposureMatch:
    """The explainable result of one deterministic exposure lookup."""

    status: str
    asset_keys: tuple[str, ...]
    matched_by: tuple[str, ...]
    reason: str


_ASSET_ALIASES: dict[str, tuple[str, ...]] = {
    "dxy": ("UUP", "DXY", "美元指数", "美元走强", "美元走弱", "美元汇率"),
    "sp500": ("SPY", "SPX", "^GSPC", "S&P 500", "S&P500", "标普500", "标普 500", "标普"),
    "nasdaq": ("QQQ", "NDX", "^IXIC", "NASDAQ-100", "NASDAQ 100", "纳斯达克100", "纳斯达克 100", "纳斯达克", "纳指"),
    "us_dividend": ("SCHD", "美股红利", "美国红利 ETF"),
    "vix": ("VIX", "^VIX", "恐慌指数"),
    "bitcoin": ("BTC", "BTC-USD", "Bitcoin", "比特币"),
    "ethereum": ("ETH", "ETH-USD", "Ethereum", "以太坊"),
    "hype": ("HYPE", "Hyperliquid"),
    "shanghai": ("000001.SH", "sh000001", "上证指数", "上证", "沪指"),
    "star50": ("000688.SH", "sh000688", "科创50", "科创 50", "科创板50", "科创板 50"),
    "china_dividend": ("000015.SH", "sh000015", "中证红利", "红利指数"),
    "nikkei": ("^N225", "N225", "Nikkei 225", "日经225", "日经 225", "日经", "日本股市"),
    "kospi": ("^KS11", "KS11", "KOSPI", "韩国综合指数", "韩国股市"),
    "wti": ("CL=F", "WTI", "West Texas Intermediate", "原油", "石油", "油价", "美油", "布伦特"),
    "gold": (
        "MGC 2610", "MGCV26.CMX", "GC=F", "XAUUSD", "XAU", "gold", "黄金价格",
        "黄金期货", "现货黄金", "黄金ETF", "黄金市场", "黄金需求", "黄金储备",
        "黄金矿", "黄金股", "买黄金", "卖黄金", "金价", "贵金属",
    ),
    "silver": ("SIL 2612", "SILZ26.CMX", "SI=F", "XAGUSD", "XAG", "silver", "白银", "银价"),
}

# Company stories are exposure to the index/asset that the user actually
# reviews, not new assets in the universe.  These are explicit table entries,
# not an LLM inference.
_CONSTITUENT_TICKER_ASSETS: dict[str, tuple[str, ...]] = {
    "NVDA": ("sp500", "nasdaq"), "NVIDIA": ("sp500", "nasdaq"), "英伟达": ("sp500", "nasdaq"),
    "MU": ("sp500", "nasdaq"), "MICRON": ("sp500", "nasdaq"), "美光": ("sp500", "nasdaq"),
    "SNDK": ("sp500", "nasdaq"), "SANDISK": ("sp500", "nasdaq"), "闪迪": ("sp500", "nasdaq"),
    "AMD": ("sp500", "nasdaq"), "TSM": ("sp500", "nasdaq"), "TSMC": ("sp500", "nasdaq"),
    "台积电": ("sp500", "nasdaq"), "ASML": ("sp500", "nasdaq"), "AVGO": ("sp500", "nasdaq"),
    "AAPL": ("sp500", "nasdaq"), "APPLE": ("sp500", "nasdaq"), "苹果": ("sp500", "nasdaq"),
    "MSFT": ("sp500", "nasdaq"), "MICROSOFT": ("sp500", "nasdaq"), "微软": ("sp500", "nasdaq"),
    "AMZN": ("sp500", "nasdaq"), "AMAZON": ("sp500", "nasdaq"), "亚马逊": ("sp500", "nasdaq"),
    "GOOGL": ("sp500", "nasdaq"), "GOOGLE": ("sp500", "nasdaq"), "谷歌": ("sp500", "nasdaq"),
    "META": ("sp500", "nasdaq"), "FACEBOOK": ("sp500", "nasdaq"), "TSLA": ("sp500", "nasdaq"),
    "特斯拉": ("sp500", "nasdaq"), "ORCL": ("sp500", "nasdaq"), "PLTR": ("sp500", "nasdaq"),
    "JPM": ("sp500", "us_dividend"), "JPMORGAN": ("sp500", "us_dividend"), "摩根大通": ("sp500", "us_dividend"),
    "XOM": ("sp500", "us_dividend"), "EXXON": ("sp500", "us_dividend"), "埃克森美孚": ("sp500", "us_dividend"),
    "NEM": ("sp500", "us_dividend", "gold"), "NEWMONT": ("sp500", "us_dividend", "gold"),
    "COIN": ("sp500", "bitcoin"), "COINBASE": ("sp500", "bitcoin"),
    "MSTR": ("sp500", "bitcoin"), "MICROSTRATEGY": ("sp500", "bitcoin"),
}

_MACRO_RULES: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
    (
        "us_macro",
        re.compile(
            r"\b(?:fomc|fed|federal reserve|powell|cpi|pce|nfp|nonfarm payrolls?|"
            r"jackson hole)\b|美联储|联储|非农|消费者价格|通胀|利率决议|"
            r"降息|加息|就业数据|鲍威尔|杰克逊霍尔",
            re.IGNORECASE,
        ),
        ("dxy", "sp500", "nasdaq", "vix", "gold", "silver", "bitcoin", "ethereum", "hype"),
    ),
    (
        "china_macro",
        re.compile(r"中国人民银行|人民银行|社融|新增信贷|中国\s*PMI|A股|中国经济|中国政策", re.IGNORECASE),
        ("shanghai", "star50", "china_dividend"),
    ),
    (
        "japan_macro",
        re.compile(r"日本央行|日银|日本利率|日经|Nikkei", re.IGNORECASE),
        ("nikkei",),
    ),
    (
        "korea_macro",
        re.compile(r"韩国央行|韩国利率|韩国综合指数|韩国股市|KOSPI", re.IGNORECASE),
        ("kospi",),
    ),
    (
        "risk_event",
        re.compile(r"\b(?:war|sanction|tariff|trade war|geopolitical)\b|战争|冲突|制裁|关税|贸易战|地缘", re.IGNORECASE),
        ("sp500", "nasdaq", "vix", "gold", "wti"),
    ),
)


def _contains_alias(text: str, alias: str) -> bool:
    if any("\u4e00" <= char <= "\u9fff" for char in alias):
        return alias in text
    upper_text = text.upper()
    upper_alias = alias.upper()
    return bool(re.search(
        r"(?<![A-Z0-9])" + re.escape(upper_alias) + r"(?![A-Z0-9])",
        upper_text,
    ))


def _iter_tickers(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            value = [value]
    if isinstance(value, (list, tuple, set)):
        for item in value:
            if item is not None and str(item).strip():
                yield str(item).strip()


def match_article_exposure(
    title: str | None,
    content: str | None,
    tickers: Any = None,
) -> ExposureMatch:
    """Match an article to approved assets using only explicit lookup rules."""
    text = f"{title or ''}\n{(content or '')[:2000]}"
    found: set[str] = set()
    matched_by: set[str] = set()

    for raw_ticker in _iter_tickers(tickers):
        normalized = raw_ticker.strip().upper()
        for key, aliases in _ASSET_ALIASES.items():
            if any(normalized == alias.upper() for alias in aliases):
                found.add(key)
                matched_by.add(f"asset:{key}")
        for alias, assets in _CONSTITUENT_TICKER_ASSETS.items():
            if normalized == alias.upper():
                found.update(assets)
                matched_by.add(f"constituent:{alias}")

    for key, aliases in _ASSET_ALIASES.items():
        if any(_contains_alias(text, alias) for alias in aliases):
            found.add(key)
            matched_by.add(f"text:{key}")

    for alias, assets in _CONSTITUENT_TICKER_ASSETS.items():
        if _contains_alias(text, alias):
            found.update(assets)
            matched_by.add(f"constituent:{alias}")

    for rule_name, pattern, assets in _MACRO_RULES:
        if pattern.search(text):
            found.update(assets)
            matched_by.add(f"macro:{rule_name}")

    asset_keys = tuple(key for key in APPROVED_ASSET_KEYS if key in found)
    if not asset_keys:
        return ExposureMatch(
            status="unmatched",
            asset_keys=(),
            matched_by=(),
            reason="no_approved_exposure",
        )
    return ExposureMatch(
        status="matched",
        asset_keys=asset_keys,
        matched_by=tuple(sorted(matched_by)),
        reason=";".join(sorted(matched_by)),
    )
