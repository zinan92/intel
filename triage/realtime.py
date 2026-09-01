"""LLM-backed triage for the realtime news lane."""

from __future__ import annotations

import json
import re
from typing import Any

from llm.deepseek import DeepSeekClient

BUCKETS = frozenset({"high_impact", "watch", "noise", "unknown"})
DIRECTIONS = frozenset({"bullish", "bearish", "mixed", "unclear"})
_HIGH_IMPACT_RE = re.compile(
    r"\b(?:fomc|cpi|pce|nfp|nonfarm payroll|jackson hole|fed decision|rate decision|"
    r"central bank|emergency rate|ecb|boj)\b|美联储|非农|消费者价格|通胀数据|"
    r"利率决议|央行|杰克逊霍尔|紧急降息|紧急加息",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """你是面向活跃交易者的实时市场新闻 triage analyst。

对每条新闻输出一个 bucket：
- high_impact：会改变宏观定价、行业预期或大型资产风险的重大事件。FOMC、CPI、PCE、非农、央行利率决议、重大财报、战争/制裁/交易所事故等，即使方向不确定，也必须是 high_impact。
- watch：影响可能存在，但幅度、可信度或传导路径还不够大；必须写清楚接下来观察什么。
- noise：没有可信的交易决策影响，例如常规公关稿、重复摘要、低流动性代币动态或无关内容。
- unknown：信息不足，或无法可靠判断；不要把不确定性伪装成 noise。

direction 只能是 bullish、bearish、mixed、unclear。affected_assets 是可能受影响的资产，保留真实 ticker；不要捏造 ticker。scenario_bull/scenario_bear 是条件推演，不是确定预测。

只返回 JSON object：{"results":[{"id":整数,"bucket":"...","direction":"...","rationale":"...","affected_assets":[{"symbol":"...","name":"...","impact":"up/down/mixed"}],"watch_for":["..."],"scenario_bull":"...","scenario_bear":"..."}]}。不要输出 Markdown 或额外解释。"""


def _extract_results(text: str) -> list[dict[str, Any]]:
    """Extract the provider's results array from a JSON-only response."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if not match:
            match = re.search(r"(\{[\s\S]*\})", text)
        if not match:
            raise
        payload = json.loads(match.group(1))
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("triage response must contain a results list")
    return [item for item in payload["results"] if isinstance(item, dict)]


def _as_text(value: Any, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _normalize_assets(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    assets: list[dict[str, str]] = []
    for item in value[:8]:
        if isinstance(item, dict):
            symbol = _as_text(item.get("symbol") or item.get("ticker"), limit=40)
            name = _as_text(item.get("name"), limit=80)
            impact = _as_text(item.get("impact"), limit=20)
        elif isinstance(item, str):
            symbol, name, impact = item.strip()[:40], "", ""
        else:
            continue
        if symbol or name:
            assets.append({"symbol": symbol, "name": name, "impact": impact})
    return assets


def _normalize_watch_for(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_text(item, limit=160) for item in value[:4] if _as_text(item, limit=160)]


def _has_high_impact_floor(article: dict[str, Any]) -> bool:
    text = f"{article.get('title') or ''} {article.get('content') or ''}"
    return bool(_HIGH_IMPACT_RE.search(text))


class RealtimeTriage:
    """Batch realtime News Items through the configured DeepSeek client."""

    def __init__(self, *, client: Any | None = None, batch_size: int = 10) -> None:
        self.client = client or DeepSeekClient()
        self.batch_size = batch_size

    @property
    def model_name(self) -> str:
        return str(getattr(self.client, "model", "deepseek"))

    def triage_batch(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return one validated triage result for every supplied article."""
        if not articles:
            return []
        prompt_parts = []
        for article in articles:
            prompt_parts.append(
                f"[id={article['id']} source={article.get('source', 'unknown')}]\n"
                f"Title: {article.get('title') or '(no title)'}\n"
                f"Content: {(article.get('content') or '')[:1800]}"
            )
        response = self.client.complete(
            "请分析以下实时新闻，返回 JSON only：\n\n" + "\n---\n".join(prompt_parts),
            system_prompt=SYSTEM_PROMPT,
            json_mode=True,
            timeout=120,
            max_tokens=max(4096, len(articles) * 500),
        )
        raw_results = _extract_results(response)
        by_id = {item.get("id"): item for item in raw_results}
        normalized: list[dict[str, Any]] = []
        for article in articles:
            result = by_id.get(article["id"])
            if result is None:
                raise ValueError(f"triage response missing id {article['id']}")
            bucket = _as_text(result.get("bucket"), limit=30)
            if bucket not in BUCKETS:
                raise ValueError(f"invalid triage bucket: {bucket}")
            direction = _as_text(result.get("direction"), limit=20) or "unclear"
            if direction not in DIRECTIONS:
                raise ValueError(f"invalid triage direction: {direction}")
            if _has_high_impact_floor(article):
                bucket = "high_impact"
            normalized.append({
                "id": article["id"],
                "bucket": bucket,
                "direction": direction,
                "rationale": _as_text(result.get("rationale"), limit=500),
                "affected_assets": _normalize_assets(result.get("affected_assets")),
                "watch_for": _normalize_watch_for(result.get("watch_for")),
                "scenario_bull": _as_text(result.get("scenario_bull"), limit=600),
                "scenario_bear": _as_text(result.get("scenario_bear"), limit=600),
            })
        return normalized
