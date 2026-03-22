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

    return f"""你是一位资深交易分析师，用中文撰写 Narrative Signal 简报。Ticker、专业术语、数据源名称保留英文。

当前时间: {date_str}

跨源验证事件:
{events_text}

最近文章 ({len(articles)} 篇):
{articles_text}

请严格按照以下格式输出:

🎯 {date_str} — 叙事信号

📊 分析 [N] 篇文章 | [N] 个高确信信号 | 主线叙事: [前3个主题]

每个主要叙事聚类（2-5个）用以下格式:

━━━ 🔥 [主题名称] ━━━

[编号]. **[一句话标题]** | [高/中/低] 确信度 | [时间框架]
   → [相关 ticker]: [发生了什么、为什么重要] | 市场盲点: [市场忽略了什么]
   → 确信度: [高/中/低] — [为什么给这个确信度]

所有聚类之后:

━━━ 📌 其他值得关注 ━━━
• [每条一句话，3-8条]

⚡️ 跨叙事关联
• [跨主题关联分析1]
• [跨主题关联分析2]
• [跨主题关联分析3]

🔗 数据交叉验证
• [数据交叉验证1]
• [数据交叉验证2]

---
数据源: [列出主要来源] | 信号比: [高确信数]/[总信号数]

要求：具体到 ticker、价格、百分比。A股/港股内容用中文，美股/全球内容也用中文描述但 ticker 保留英文。像一个中国交易员写给自己的笔记。"""


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
