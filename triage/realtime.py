"""LLM-backed triage for the realtime news lane."""

from __future__ import annotations

import json
import re
from typing import Any

from llm.deepseek import DeepSeekClient, DeepSeekError

BUCKETS = frozenset({"high_impact", "watch", "noise", "unknown"})
DIRECTIONS = frozenset({"bullish", "bearish", "unclear"})
ASSET_IMPACTS = frozenset({"up", "down"})
_HIGH_IMPACT_RE = re.compile(
    r"\b(?:fomc|cpi|pce|nfp|nonfarm payroll|jackson hole|fed decision|rate decision|"
    r"emergency rate|(?:fed|ecb|boj|central bank) (?:rate )?decision)\b|"
    r"非农|消费者价格|通胀数据|利率决议|杰克逊霍尔|紧急降息|紧急加息|"
    r"(?:美联储|欧洲央行|日本央行|央行).{0,20}(?:加息|降息|利率决定|利率决议)",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """你是面向活跃交易者的实时市场新闻 triage analyst。

对每条新闻输出一个 bucket：
- high_impact：会改变宏观定价、行业预期或大型资产风险的重大事件。FOMC、CPI、PCE、非农、央行利率决议、重大财报、战争/制裁/交易所事故等，即使方向不确定，也必须是 high_impact。
- watch：影响可能存在，但幅度、可信度或传导路径还不够大；必须写清楚接下来观察什么。
- noise：没有可信的交易决策影响，例如常规公关稿、重复摘要、低流动性代币动态或无关内容。
- unknown：信息不足，或无法可靠判断；不要把不确定性伪装成 noise。

direction 只能是 bullish、bearish、unclear，不允许 mixed。direction 表示主要交易方向；不同资产可在 affected_assets 中分别标 up/down。
- high_impact 必须选择 bullish 或 bearish，并至少给出一个受影响资产；不要捏造证券 ticker，可使用真实指数、利率、外汇、商品或加密资产符号/名称。
- watch 若方向 unclear，watch_for 必须给出具体、可观察的确认条件。
- noise/unknown 不得伪造方向或资产。
- 只给一个明确判断及传导理由，不要输出 bull/bear 两套 if 情景。

只返回 JSON object：{"results":[{"id":整数,"bucket":"...","direction":"...","rationale":"...","affected_assets":[{"symbol":"...","name":"...","impact":"up/down"}],"watch_for":["..."]}]}。不要输出 Markdown 或额外解释。"""


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


def _article_prompt(article: dict[str, Any]) -> str:
    tickers = article.get("tickers")
    ticker_text = ", ".join(str(value) for value in tickers) if tickers else "none"
    return (
        f"[id={article['id']} source={article.get('source', 'unknown')}]\n"
        f"Title: {article.get('title') or '(no title)'}\n"
        f"Content: {(article.get('content') or '')[:1800]}\n"
        f"Verified source tickers: {ticker_text}"
    )


def _normalize_result(
    article: dict[str, Any],
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    if result is None:
        raise ValueError("triage response missing article id")
    bucket = _as_text(result.get("bucket"), limit=30)
    if bucket not in BUCKETS:
        raise ValueError(f"invalid triage bucket: {bucket}")
    if _has_high_impact_floor(article):
        bucket = "high_impact"

    direction = _as_text(result.get("direction"), limit=20) or "unclear"
    if direction not in DIRECTIONS:
        raise ValueError(f"invalid triage direction: {direction}")
    rationale = _as_text(result.get("rationale"), limit=500)
    if not rationale:
        raise ValueError("rationale must be non-empty")
    assets = _normalize_assets(result.get("affected_assets"))
    watch_for = _normalize_watch_for(result.get("watch_for"))

    if bucket == "high_impact":
        if direction not in {"bullish", "bearish"}:
            raise ValueError("high_impact direction must be bullish or bearish")
        if not assets:
            raise ValueError("high_impact affected_assets must be non-empty")
        if any(asset.get("impact") not in ASSET_IMPACTS for asset in assets):
            raise ValueError("high_impact asset impact must be up or down")
    if bucket == "watch" and direction == "unclear" and not watch_for:
        raise ValueError("unclear watch result requires non-empty watch_for")

    return {
        "id": article["id"],
        "bucket": bucket,
        "direction": direction,
        "rationale": rationale,
        "affected_assets": assets,
        "watch_for": watch_for,
    }


def _isolated_failure(article: dict[str, Any], error: Exception) -> dict[str, Any]:
    return {
        "id": article["id"],
        "bucket": "unknown",
        "direction": "unclear",
        "rationale": "AI output failed the decision contract and is queued for retry.",
        "affected_assets": [],
        "watch_for": ["retry analysis"],
        "validation_error": str(error)[:300],
    }


class RealtimeTriage:
    """Batch realtime News Items through the configured DeepSeek client."""

    def __init__(self, *, client: Any | None = None, batch_size: int = 10) -> None:
        self.client = client or DeepSeekClient()
        self.batch_size = batch_size
        self._provider = "deepseek"

    @property
    def model_name(self) -> str:
        if self._provider == "codex-cli":
            return "codex-cli"
        return str(getattr(self.client, "model", "deepseek"))

    def _complete(self, prompt: str) -> str:
        """Use DeepSeek first, then the existing isolated Codex fallback."""
        try:
            self._provider = "deepseek"
            return self.client.complete(
                prompt,
                system_prompt=SYSTEM_PROMPT,
                json_mode=True,
                timeout=120,
                max_tokens=max(4096, self.batch_size * 500),
            )
        except DeepSeekError:
            from scripts.generate_narrative_signal import _call_codex

            fallback, provider = _call_codex(
                f"{SYSTEM_PROMPT}\n\n{prompt}"
            )
            if not fallback or provider != "codex-cli":
                raise
            self._provider = provider
            return fallback

    def triage_batch(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return one validated triage result for every supplied article."""
        if not articles:
            return []
        prompt_parts = [_article_prompt(article) for article in articles]
        response = self._complete(
            "请分析以下实时新闻，返回 JSON only：\n\n"
            + "\n---\n".join(prompt_parts)
        )
        initial_parse_error: Exception | None = None
        try:
            raw_results = _extract_results(response)
        except Exception as exc:
            raw_results = []
            initial_parse_error = exc
        by_id = {item.get("id"): item for item in raw_results}
        normalized_by_id: dict[Any, dict[str, Any]] = {}
        invalid: list[tuple[dict[str, Any], Exception]] = []
        for article in articles:
            try:
                if initial_parse_error is not None:
                    raise initial_parse_error
                normalized_by_id[article["id"]] = _normalize_result(
                    article,
                    by_id.get(article["id"]),
                )
            except Exception as exc:
                invalid.append((article, exc))

        if invalid:
            repair_prompt = (
                "修复以下不符合 decision contract 的结果。必须逐条返回；"
                "High Impact 必须 bullish/bearish 且 affected_assets 非空，"
                "Watch+unclear 必须有具体 watch_for；不得输出 mixed 或双情景。\n\n"
                + "\n---\n".join(
                    f"Validation error: {error}\n{_article_prompt(article)}"
                    for article, error in invalid
                )
            )
            try:
                repair_results = _extract_results(self._complete(repair_prompt))
                repair_by_id = {item.get("id"): item for item in repair_results}
            except Exception:
                repair_by_id = {}
            for article, first_error in invalid:
                try:
                    normalized_by_id[article["id"]] = _normalize_result(
                        article,
                        repair_by_id.get(article["id"]),
                    )
                except Exception as repair_error:
                    normalized_by_id[article["id"]] = _isolated_failure(
                        article,
                        repair_error if repair_by_id else first_error,
                    )

        return [normalized_by_id[article["id"]] for article in articles]
