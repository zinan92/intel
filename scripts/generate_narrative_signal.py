"""Generate Narrative Signal brief using Claude CLI."""
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timedelta

from db.database import get_session, init_db
from db.models import Article
from events.models import Event
from briefs.models import Brief

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _call_claude(prompt: str) -> str | None:
    claude_path = shutil.which("claude")
    if not claude_path:
        logger.error("claude CLI not found")
        return None
    try:
        result = subprocess.run(
            [claude_path, "-p", prompt, "--output-format", "text"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            logger.error("claude CLI error: %s", result.stderr[:300])
            return None
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error("claude CLI timed out (120s)")
        return None
    except Exception:
        logger.exception("claude CLI failed")
        return None


def _build_prompt(articles: list[Article], events: list[Event]) -> str:
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d %H:%M UTC")

    # Format articles
    articles_text = ""
    for i, a in enumerate(articles[:80], 1):
        title = (a.title or "").strip()[:100]
        source = a.source
        tags = ""
        if a.narrative_tags:
            try:
                tags = ", ".join(json.loads(a.narrative_tags)[:3])
            except Exception:
                pass
        content_snippet = (a.content or "")[:150].strip()
        articles_text += f"{i}. [{source}] {title}"
        if tags:
            articles_text += f" | tags: {tags}"
        if content_snippet:
            articles_text += f"\n   {content_snippet}"
        articles_text += "\n"

    # Format events
    events_text = ""
    for e in events[:10]:
        tag = e.narrative_tag.replace("-", " ")
        events_text += f"- {tag} (signal {e.signal_score:.1f}, {e.source_count} sources)"
        if e.narrative_summary:
            events_text += f"\n  {e.narrative_summary[:150]}"
        events_text += "\n"

    return f"""You are a senior trading analyst producing a Narrative Signal brief.

Current time: {date_str}

ACTIVE CROSS-SOURCE EVENTS:
{events_text}

RECENT ARTICLES ({len(articles)} total):
{articles_text}

Produce a Narrative Signal brief in this EXACT format:

🎯 {date_str} — Narrative Signals

📊 [N] articles analyzed | [N] high signals | Top narratives: [top-3-tags]

For each major narrative cluster (2-5 clusters), use this format:

━━━ 🔥 [THEME NAME] ━━━

[Number]. **[One-line headline]** | [H/M/L conviction] | [Timeframe]
   → [Relevant tickers]: [What happened and why it matters] | Edge: [What the market is missing]
   → Conviction: [H/M/L] — [Why this conviction level]

After all clusters, add:

━━━ 📌 Other Notable ━━━
• [1-line bullet for each minor signal, 3-8 items]

⚡️ CROSS-NARRATIVE
• [Cross-theme connection 1]
• [Cross-theme connection 2]
• [Cross-theme connection 3]

🔗 QUANT CHECK
• [Data point cross-reference 1]
• [Data point cross-reference 2]

---
Sources: [list key sources] | Signal ratio: [high-conviction-count]/[total-signals]

Be specific about tickers, prices, percentages. Use Chinese for A-share/HK content, English for US/global. Mix languages naturally like a bilingual trader would."""


def generate_brief(limit: int = 100) -> int | None:
    """Generate a narrative signal brief. Returns brief ID or None on failure."""
    init_db()
    session = get_session()

    try:
        now = datetime.utcnow()

        # Get recent articles
        cutoff = now - timedelta(hours=6)
        articles = (
            session.query(Article)
            .filter(Article.collected_at >= cutoff)
            .order_by(Article.collected_at.desc())
            .limit(limit)
            .all()
        )

        if len(articles) < 5:
            logger.warning("Only %d articles in last 6h, skipping brief", len(articles))
            return None

        # Get active events
        events = (
            session.query(Event)
            .filter(Event.status == "active", Event.source_count >= 2)
            .order_by(Event.signal_score.desc())
            .limit(10)
            .all()
        )

        prompt = _build_prompt(articles, events)
        logger.info("Generating brief from %d articles, %d events...", len(articles), len(events))

        content = _call_claude(prompt)
        if not content:
            logger.error("Failed to generate brief")
            return None

        # Count signals (lines with conviction markers)
        signal_count = content.count("| H |") + content.count("| M |") + content.count("| L |")
        signal_count += content.count("Conviction: H") + content.count("Conviction: M") + content.count("Conviction: L")

        brief = Brief(
            content=content,
            article_count=len(articles),
            signal_count=max(signal_count, 1),
            status="published",
        )
        session.add(brief)
        session.commit()

        logger.info("Brief #%d generated: %d chars, %d signals", brief.id, len(content), brief.signal_count)
        return brief.id

    finally:
        session.close()


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    brief_id = generate_brief(limit)
    if brief_id:
        print(f"Brief #{brief_id} generated successfully")
    else:
        print("Brief generation failed or skipped")
