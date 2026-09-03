"""DeepSeek-based article relevance scoring and narrative tagging."""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from llm.codex import CodexCLIClient
from llm.deepseek import DeepSeekClient, DeepSeekError

logger = logging.getLogger(__name__)


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from text that may contain surrounding prose or markdown."""
    import re

    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            return parsed["results"]
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding a bare JSON array in the text
    m = re.search(r"\[[\s\S]*\]", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No JSON array found in response", text, 0)

_SYSTEM_PROMPT = """You are a trading analyst assistant. For each article, you must:

1. Rate its **relevance_score** (1-5) for an active multi-market trader:
   - 5: ONLY for breaking/major events — surprise rate decision, major earnings miss/beat, geopolitical shock, market crash/surge. Must be immediately actionable. Daily market wraps and routine summaries are NEVER 5.
   - 4: High relevance — sector trend, significant macro data, important KOL thesis with clear trading implication
   - 3: Moderate — general market commentary, industry news. Default for routine "markets wrap" or "daily recap" articles.
   - 2: Low — tangentially related to markets. GitHub repos with empty/minimal descriptions cap at 2.
   - 1: Noise — not useful for trading decisions

2. Generate **narrative_tags** — short descriptive phrases (2-4 words each) capturing the article's trading-relevant narrative. Examples: "nvidia-earnings-beat", "fed-rate-pause", "btc-etf-inflows", "china-stimulus-hope".

Respond with a JSON object whose "results" value is an array. Each array element must have:
- "id": the article id (integer)
- "relevance_score": integer 1-5
- "narrative_tags": list of 1-3 short narrative tag strings

Example JSON response:
{"results": [
  {"id": 1, "relevance_score": 4, "narrative_tags": ["nvidia-earnings-beat", "ai-capex-growth"]},
  {"id": 2, "relevance_score": 2, "narrative_tags": ["general-market-commentary"]}
]}

Respond ONLY with the JSON object, no other text."""

# Pause between API calls to avoid hammering
_MIN_INTERVAL = 2.0


class TaggingError(RuntimeError):
    """Raised when neither provider returns a complete valid scoring batch."""


@dataclass(frozen=True)
class TagBatchResult:
    items: tuple[dict[str, Any], ...]
    provider: str
    fallback_reason: str | None = None


class LLMTagger:
    """Batch LLM tagger with DeepSeek primary and Codex fallback."""

    def __init__(
        self,
        batch_size: int = 10,
        client: DeepSeekClient | None = None,
        fallback_client: CodexCLIClient | None = None,
    ) -> None:
        self.batch_size = batch_size
        self.client = client or DeepSeekClient()
        self.fallback_client = fallback_client or CodexCLIClient()
        self._last_call = 0.0
        self._batches_processed = 0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call = time.time()

    @staticmethod
    def _validate(text: str, articles: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        results = _extract_json_array(text)
        expected_ids = {int(article["id"]) for article in articles}
        valid: list[dict[str, Any]] = []
        seen: set[int] = set()
        for result in results:
            if not isinstance(result, dict):
                continue
            article_id = result.get("id")
            score = result.get("relevance_score")
            tags = result.get("narrative_tags")
            if not isinstance(article_id, int) or article_id not in expected_ids or article_id in seen:
                continue
            if not isinstance(score, int) or not 1 <= score <= 5:
                continue
            if not isinstance(tags, list) or not tags:
                continue
            clean_tags = [str(tag).strip() for tag in tags[:3] if str(tag).strip()]
            if not clean_tags:
                continue
            seen.add(article_id)
            valid.append({
                "id": article_id,
                "relevance_score": score,
                "narrative_tags": clean_tags,
            })
        if seen != expected_ids:
            raise TaggingError("provider returned an incomplete or invalid result set")
        return tuple(valid)

    def tag_batch(self, articles: list[dict[str, Any]]) -> TagBatchResult:
        """Tag a batch of articles. Each dict needs 'id', 'title', 'content'.

        Returns validated items plus provider provenance.
        """
        if not articles:
            return TagBatchResult((), "none")

        # Build prompt with articles
        parts = []
        for a in articles:
            title = a.get("title") or "(no title)"
            content = (a.get("content") or "")[:1000]
            source = a.get("source", "unknown")
            parts.append(f"[Article ID={a['id']}, source={source}]\nTitle: {title}\nContent: {content}\n")

        user_msg = "Here are the articles to score. Return JSON only:\n\n" + "\n---\n".join(parts)

        self._rate_limit()
        try:
            text = self.client.complete(
                user_msg,
                system_prompt=_SYSTEM_PROMPT,
                json_mode=True,
                timeout=120,
                max_tokens=4096,
            )
            items = self._validate(text, articles)
            self._batches_processed += 1
            return TagBatchResult(items, "deepseek")
        except DeepSeekError as exc:
            fallback_reason = type(exc).__name__
            logger.warning("DeepSeek tagging failed; using Codex fallback (%s)", fallback_reason)
        except (json.JSONDecodeError, TaggingError):
            fallback_reason = "invalid_primary_output"
            logger.warning("DeepSeek tagging output was invalid; using Codex fallback")

        try:
            text = self.fallback_client.complete(
                user_msg,
                system_prompt=_SYSTEM_PROMPT,
                json_mode=True,
                timeout=300,
                max_tokens=4096,
            )
            items = self._validate(text, articles)
            self._batches_processed += 1
            return TagBatchResult(items, "codex-cli", fallback_reason)
        except Exception as exc:
            raise TaggingError("both providers failed to return a valid scoring batch") from exc

    @property
    def batches_processed(self) -> int:
        return self._batches_processed
