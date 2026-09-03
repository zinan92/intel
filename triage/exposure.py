"""Deterministic realtime exposure matching backed by Park's target registry."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "config" / "park-exposure-registry.yaml"


def _load_registry() -> dict[str, Any]:
    with REGISTRY_PATH.open(encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)
    if not isinstance(registry, dict):
        raise ValueError(f"Exposure registry must be a mapping: {REGISTRY_PATH}")
    if not isinstance(registry.get("sectors"), list):
        raise ValueError(f"Exposure registry has no sectors: {REGISTRY_PATH}")
    if not isinstance(registry.get("matching", {}).get("aliases", []), list):
        raise ValueError(f"Exposure registry aliases must be a list: {REGISTRY_PATH}")
    return registry


_REGISTRY = _load_registry()
EXPOSURE_UNIVERSE_VERSION = f"park-exposure-registry-v{_REGISTRY['version']}"


# Keep this order stable. It is the same 16-asset universe used by the Human
# K-line Review / Daily K-line products. The legacy asset matcher below is
# intentionally preserved so this registry migration is additive.
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
    targets: tuple[dict[str, Any], ...] = ()


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


# Company stories remain linked to the same market assets as before. This map
# is retained verbatim from macro-assets-v3 so the registry migration cannot
# silently change the existing 16-asset gate.
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


# Existing macro-to-asset behavior is deliberately unchanged. Registry aliases
# add structured target identities alongside these canonical asset keys.
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


def _target_record(raw: Mapping[str, Any], sector: Mapping[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": str(raw["type"]),
        "id": str(raw["id"]),
        "name": str(raw.get("name", raw["id"])),
        "sector": str(sector["name"]),
        "macro": str(sector["macro"]),
    }
    for field in ("market", "ticker", "listed", "reason", "links_assets", "listed_at"):
        if field in raw:
            record[field] = raw[field]
    if (
        record.get("market") == "CN"
        and "ticker" not in record
        and re.fullmatch(r"\d{6}", record["id"])
    ):
        record["ticker"] = record["id"]
    return record


def _build_registry_targets() -> tuple[dict[str, Any], ...]:
    records: list[dict[str, Any]] = []
    for sector in _REGISTRY["sectors"]:
        for raw in sector.get("targets", []):
            records.append(_target_record(raw, sector))
    return tuple(records)


_REGISTRY_TARGETS = _build_registry_targets()
_TARGETS_BY_ID: dict[str, tuple[dict[str, Any], ...]] = {}
for _record in _REGISTRY_TARGETS:
    _TARGETS_BY_ID.setdefault(_record["id"], tuple())
    _TARGETS_BY_ID[_record["id"]] += (_record,)


def _asset_registry_targets() -> dict[str, dict[str, Any]]:
    raw_assets = {str(asset["id"]): asset for asset in _REGISTRY.get("assets", [])}
    registry_ids = {
        "dxy": "DXY", "sp500": "SPX", "nasdaq": "NDX", "us_dividend": "SCHD", "vix": "VIX",
        "bitcoin": "BTC", "ethereum": "ETH", "hype": "HYPE", "shanghai": "SSE", "star50": "STAR50",
        "china_dividend": "SSE_DIV", "nikkei": "N225", "kospi": "KOSPI", "wti": "WTI", "gold": "XAU", "silver": "XAG",
    }
    result: dict[str, dict[str, Any]] = {}
    for key, registry_id in registry_ids.items():
        raw = raw_assets.get(registry_id, {})
        result[key] = {
            "type": "asset",
            "id": key,
            "name": raw.get("name", key),
            "market": raw.get("market"),
            "kind": raw.get("kind"),
        }
    return result


_ASSET_TARGETS = _asset_registry_targets()

def _alias_rules() -> tuple[tuple[str, tuple[str, ...], tuple[dict[str, Any], ...]], ...]:
    rules: list[tuple[str, tuple[str, ...], tuple[dict[str, Any], ...]]] = []
    for raw in _REGISTRY.get("matching", {}).get("aliases", []):
        rule_id = str(raw["id"])
        terms = tuple(str(term) for term in raw.get("terms", []))
        target_ids = raw.get("targets", raw.get("target", []))
        if isinstance(target_ids, str):
            target_ids = [target_ids]
        records = tuple(
            record
            for target_id in target_ids
            for record in _TARGETS_BY_ID.get(str(target_id), ())
        )
        if not records:
            raise ValueError(f"Registry alias {rule_id!r} points to no target")
        rules.append((rule_id, terms, records))
    return tuple(rules)


_ALIAS_RULES = _alias_rules()
_CONTENT_CHARS = int(_REGISTRY.get("matching", {}).get("content_chars", 2000))


def _record_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record["type"]),
        str(record["id"]),
        str(record.get("sector", "")),
        str(record.get("macro", "")),
    )


def _append_target(targets: dict[tuple[str, str, str, str], dict[str, Any]], record: Mapping[str, Any]) -> None:
    key = _record_key(record)
    if key not in targets:
        targets[key] = dict(record)


def _match_registry_targets(
    text: str,
    targets: dict[tuple[str, str, str, str], dict[str, Any]],
    matched_by: set[str],
) -> None:
    for record in _REGISTRY_TARGETS:
        candidates = (record["id"], record["name"], record.get("ticker", ""))
        if any(_contains_alias(text, candidate) for candidate in candidates if candidate):
            _append_target(targets, record)
            matched_by.add(f"target:{record['id']}")

    for rule_id, terms, records in _ALIAS_RULES:
        matched_terms = [term for term in terms if _contains_alias(text, term)]
        if not matched_terms:
            continue
        for record in records:
            _append_target(targets, record)
        matched_by.add(f"alias:{rule_id}:{'|'.join(matched_terms)}")


def match_article_exposure(
    title: str | None,
    content: str | None,
    tickers: Any = None,
) -> ExposureMatch:
    """Match an article to legacy assets and v6 registry targets deterministically."""
    text = f"{title or ''}\n{(content or '')[:_CONTENT_CHARS]}"
    ticker_values = tuple(_iter_tickers(tickers))
    lookup_text = text + ("\n" + " ".join(ticker_values) if ticker_values else "")
    found_assets: set[str] = set()
    matched_by: set[str] = set()
    targets: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for raw_ticker in ticker_values:
        normalized = raw_ticker.strip().upper()
        for key, aliases in _ASSET_ALIASES.items():
            if any(normalized == alias.upper() for alias in aliases):
                found_assets.add(key)
                matched_by.add(f"asset:{key}")

    for key, aliases in _ASSET_ALIASES.items():
        if any(_contains_alias(lookup_text, alias) for alias in aliases):
            found_assets.add(key)
            matched_by.add(f"text:{key}")

    for rule_name, pattern, assets in _MACRO_RULES:
        if pattern.search(lookup_text):
            found_assets.update(assets)
            matched_by.add(f"macro:{rule_name}")

    _match_registry_targets(lookup_text, targets, matched_by)

    for alias, assets in _CONSTITUENT_TICKER_ASSETS.items():
        if _contains_alias(lookup_text, alias):
            found_assets.update(assets)
            matched_by.add(f"constituent:{alias}")

    for key in APPROVED_ASSET_KEYS:
        if key in found_assets:
            _append_target(targets, _ASSET_TARGETS[key])

    asset_keys = tuple(key for key in APPROVED_ASSET_KEYS if key in found_assets)
    target_values = tuple(targets.values())
    if not asset_keys and not target_values:
        return ExposureMatch(
            status="unmatched",
            asset_keys=(),
            matched_by=(),
            reason="no_approved_exposure",
            targets=(),
        )
    return ExposureMatch(
        status="matched",
        asset_keys=asset_keys,
        matched_by=tuple(sorted(matched_by)),
        reason=";".join(sorted(matched_by)),
        targets=target_values,
    )
