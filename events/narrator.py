"""LLM narrative generation for cross-source events via claude CLI."""
import logging
import shutil
import subprocess
import time

from sqlalchemy.orm import Session

from db.models import Article
from events.models import Event, EventArticle

logger = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 2


def _call_claude(prompt: str) -> str | None:
    claude_path = shutil.which("claude")
    if not claude_path:
        logger.warning("claude CLI not found — narrative generation disabled")
        return None
    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("claude CLI returned %d: %s", result.returncode, result.stderr[:200])
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning("claude CLI timed out for narrative generation")
        return None
    except Exception:
        logger.exception("claude CLI failed")
        return None


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


def generate_narratives(session: Session) -> int:
    events = (
        session.query(Event)
        .filter(
            Event.status == "active",
            Event.source_count >= 2,
            Event.trading_play.is_(None),
        )
        .order_by(Event.signal_score.desc())
        .limit(10)
        .all()
    )
    if not events:
        return 0

    generated = 0
    for event in events:
        articles = (
            session.query(Article)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(EventArticle.event_id == event.id)
            .order_by(Article.relevance_score.desc().nullslast())
            .limit(3)
            .all()
        )
        if not articles:
            continue

        prompt = _build_prompt(event, articles)
        narrative = _call_claude(prompt)

        if narrative:
            summary, play = _parse_narrator_response(narrative)
            event.narrative_summary = summary
            event.trading_play = play
            generated += 1
            logger.info("[narrator] Generated narrative for '%s'", event.narrative_tag)
        else:
            logger.warning("[narrator] Failed to generate for '%s'", event.narrative_tag)

        time.sleep(_RATE_LIMIT_SECONDS)

    session.commit()
    logger.info("[narrator] Generated %d narratives (of %d candidates)", generated, len(events))
    return generated
