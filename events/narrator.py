"""LLM narrative generation for cross-source events via DeepSeek API."""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from db.models import Article
from events.models import Event, EventArticle
from llm.codex import CodexCLIClient, CodexCLIError
from llm.deepseek import DeepSeekClient, DeepSeekError

logger = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 2


@dataclass(frozen=True)
class NarrativeRunResult:
    generated: int
    failed: int
    providers: tuple[str, ...] = field(default_factory=tuple)
    fallback_reasons: tuple[str, ...] = field(default_factory=tuple)


def _call_deepseek(prompt: str) -> str:
    return DeepSeekClient().complete(prompt, timeout=30, max_tokens=2048)


def _call_codex(prompt: str) -> str:
    return CodexCLIClient().complete(prompt, timeout=300, max_tokens=2048)


def _call_llm(prompt: str) -> tuple[str | None, str | None, str | None]:
    try:
        content = _call_deepseek(prompt)
        return content, f"deepseek:{DeepSeekClient().model}", None
    except DeepSeekError as exc:
        fallback_reason = type(exc).__name__
        logger.warning("DeepSeek narrative generation failed; trying Codex: %s", fallback_reason)

    try:
        return _call_codex(prompt), "codex-cli", fallback_reason
    except CodexCLIError as exc:
        failure = f"deepseek={fallback_reason};codex={exc.reason}"
        logger.error("Both event narrative providers failed: %s", failure)
        return None, None, failure


def _parse_narrator_response(response: str) -> tuple[str, str | None]:
    """Parse narrator response into (summary, trading_play).

    trading_play format stored:
    BULL_PCT:65
    BULL: If condition, then outcome. Consider action.
    BEAR_PCT:35
    BEAR: If condition, then outcome. Consider action.
    """
    summary = response.strip()
    play = None

    # Try to find BULL_PCT marker (structured format)
    bull_idx = response.find("BULL_PCT:")
    if bull_idx == -1:
        # Fallback: try old SCENARIO A format
        marker = "SCENARIO A:"
        idx = response.find(marker)
        if idx == -1:
            return response.strip(), None
        summary = response[:idx].strip()
        play = response[idx:].strip()
        if summary.upper().startswith("SUMMARY:"):
            summary = summary[8:].strip()
        return summary, play

    # New structured format
    summary = response[:bull_idx].strip()
    if summary.upper().startswith("SUMMARY:"):
        summary = summary[8:].strip()

    play = response[bull_idx:].strip()
    return summary, play


def _build_prompt(event: Event, articles: list[Article]) -> str:
    tag_display = event.narrative_tag.replace("-", " ")
    articles_text = ""
    for i, a in enumerate(articles[:3], 1):
        title = a.title or "Untitled"
        content = (a.content or "")[:200]
        articles_text += f"\nArticle {i}: {title}\n{content}\n"
    return (
        f"You are a trading analyst. Analyze this cross-source market event.\n\n"
        f"Event: {tag_display}\n"
        f"Sources: {event.source_count} sources, {event.article_count} articles\n"
        f"{articles_text}\n"
        f"Respond in this EXACT format (keep the labels exactly as shown):\n\n"
        f"SUMMARY: [2-3 sentence summary of what happened and why it matters]\n\n"
        f"BULL_PCT: [integer 0-100, probability of bull case]\n"
        f"BULL: If [specific condition], then [expected outcome]. Consider [action with ticker and timeframe].\n\n"
        f"BEAR_PCT: [integer 0-100, probability of bear case, must equal 100 minus BULL_PCT]\n"
        f"BEAR: If [specific condition], then [expected outcome]. Consider [action with ticker and timeframe]."
    )


def _article_timestamp(article: Article):
    return article.published_at or article.collected_at


def generate_narratives(session: Session) -> NarrativeRunResult:
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=48)
    events = (
        session.query(Event)
        .filter(
            Event.status == "active",
            Event.source_count >= 2,
            Event.trading_play.is_(None),
            Event.window_start >= cutoff,
            Event.window_end >= now,
        )
        .order_by(Event.signal_score.desc())
        .limit(10)
        .all()
    )
    if not events:
        return NarrativeRunResult(generated=0, failed=0)

    generated = 0
    failed = 0
    providers: set[str] = set()
    fallback_reasons: set[str] = set()
    for event in events:
        articles = (
            session.query(Article)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(EventArticle.event_id == event.id)
            .order_by(Article.relevance_score.desc().nullslast())
            .all()
        )
        articles = [
            article for article in articles
            if event.window_start <= _article_timestamp(article) < event.window_end
        ][:3]
        if not articles:
            continue

        prompt = _build_prompt(event, articles)
        # End the read transaction before waiting on an external provider.
        session.commit()
        narrative, provider, fallback_reason = _call_llm(prompt)

        if narrative:
            summary, play = _parse_narrator_response(narrative)
            event.narrative_summary = summary
            event.trading_play = play
            event.narrative_provider = provider
            generated += 1
            if provider:
                providers.add(provider)
            if fallback_reason:
                fallback_reasons.add(fallback_reason)
            logger.info("[narrator] Generated narrative for '%s'", event.narrative_tag)
        else:
            failed += 1
            if fallback_reason:
                fallback_reasons.add(fallback_reason)
            logger.warning("[narrator] Failed to generate for '%s'", event.narrative_tag)

        # Persist each result before the next query can autoflush it and hold
        # SQLite's single writer lock across the next model call.
        session.commit()
        if event is not events[-1]:
            time.sleep(_RATE_LIMIT_SECONDS)

    session.commit()
    logger.info("[narrator] Generated %d narratives (of %d candidates)", generated, len(events))
    return NarrativeRunResult(
        generated=generated,
        failed=failed,
        providers=tuple(sorted(providers)),
        fallback_reasons=tuple(sorted(fallback_reasons)),
    )
