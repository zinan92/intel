"""LLM-based article tagger using Claude Code CLI for relevance scoring and narrative tagging."""

import json
import logging
import os
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from text that may contain surrounding prose or markdown."""
    import re

    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
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

Respond with a JSON array. Each element must have:
- "id": the article id (integer)
- "relevance_score": integer 1-5
- "narrative_tags": list of 1-3 short narrative tag strings

Example response:
[
  {"id": 1, "relevance_score": 4, "narrative_tags": ["nvidia-earnings-beat", "ai-capex-growth"]},
  {"id": 2, "relevance_score": 2, "narrative_tags": ["general-market-commentary"]}
]

Respond ONLY with the JSON array, no other text."""

# Pause between CLI calls to avoid hammering
_MIN_INTERVAL = 2.0


class LLMTagger:
    """Batch LLM tagger using Claude Code CLI."""

    def __init__(self, batch_size: int = 10) -> None:
        self.batch_size = batch_size
        self._last_call = 0.0
        self._batches_processed = 0

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        self._last_call = time.time()

    def tag_batch(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Tag a batch of articles. Each dict needs 'id', 'title', 'content'.

        Returns list of {"id": int, "relevance_score": int, "narrative_tags": list[str]}.
        """
        if not articles:
            return []

        # Build prompt with articles
        parts = []
        for a in articles:
            title = a.get("title") or "(no title)"
            content = (a.get("content") or "")[:1000]
            source = a.get("source", "unknown")
            parts.append(f"[Article ID={a['id']}, source={source}]\nTitle: {title}\nContent: {content}\n")

        user_msg = _SYSTEM_PROMPT + "\n\nHere are the articles to score:\n\n" + "\n---\n".join(parts)

        self._rate_limit()
        try:
            # Clear CLAUDECODE env var to allow nested CLI calls
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            result = subprocess.run(
                ["claude", "-p", user_msg, "--output-format", "json", "--model", "claude-sonnet-4-6"],
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )

            if result.returncode != 0:
                logger.error("claude CLI failed: %s", result.stderr.strip())
                return []

            # claude --output-format json wraps response in {"type":"result","result":"..."}
            outer = json.loads(result.stdout)
            text = outer.get("result", result.stdout).strip()

            # Sonnet may include analysis text before the JSON array.
            # Extract the JSON array from wherever it appears.
            results = _extract_json_array(text)
            self._batches_processed += 1

            # Validate
            valid = []
            for r in results:
                if isinstance(r, dict) and "id" in r and "relevance_score" in r:
                    score = r["relevance_score"]
                    if isinstance(score, int) and 1 <= score <= 5:
                        tags = r.get("narrative_tags", [])
                        if isinstance(tags, list):
                            valid.append({
                                "id": r["id"],
                                "relevance_score": score,
                                "narrative_tags": [str(t) for t in tags[:5]],
                            })
            return valid

        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response: %s", e)
            return []
        except subprocess.TimeoutExpired:
            logger.error("claude CLI timed out")
            return []
        except Exception as e:
            logger.error("claude CLI call failed: %s", e)
            return []

    @property
    def batches_processed(self) -> int:
        return self._batches_processed
