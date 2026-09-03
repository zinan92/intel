"""Generate Narrative Signal briefs with the DeepSeek Chat Completions API."""
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from llm.codex import CodexCLIClient, CodexCLIError
from db.database import get_session, init_db
from db.models import Article
from events.models import Event
from briefs.models import Brief
from scripts.brief_quality import validate_published_brief

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRIEF_TIMEZONE = ZoneInfo("Asia/Shanghai")
BRIEF_WINDOW_HOURS = 24
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
# DeepSeek documents this alias as the current V4-Flash release (V4-Flash-0731).
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_API_KEY_FILE = Path("/Users/wendy/park-hands/_secrets/deepseek-key")
CODEX_TIMEOUT_SECONDS = 300
CODEX_FALLBACK_PREFIX = """你是 Finance Newsletter 的备用叙事生成器。
只使用下方任务中已经提供的冻结文章、事件和来源文本；不得调用工具、从文件系统读取输入、访问网络、重新获取数据或补造事实。
严格遵守原任务的输出格式，只返回可供原质量门验证的正文或 JSON。
"""
SOURCE_LABELS = {
    "rss": "财经媒体",
    "google_news": "新闻聚合",
    "yahoo_finance": "财经媒体",
    "hackernews": "技术社区",
    "reddit": "投资者社区",
    "github_trending": "开发者趋势",
    "github_release": "项目发布",
    "website_monitor": "官网监控",
    "social_kol": "KOL",
    "xueqiu": "A股社交",
    "cls_telegraph": "财联社快讯",
    "eastmoney_global_news": "东方财富7x24",
}
_NOISE_TITLE_PATTERNS = [
    re.compile(r"\bno description available\b", re.I),
    re.compile(r"^\s*(ai|trading|crypto|finance)\s*-\s*no description available\s*$", re.I),
    re.compile(r"\blive\s+gold\s+trading\b", re.I),
]

_last_deepseek_failure = "not_attempted"
_last_codex_failure = "not_attempted"


@dataclass(frozen=True)
class ArticleSelection:
    articles: list[Article]
    eligible_count: int
    scored_count: int

    @property
    def coverage(self) -> float:
        return self.scored_count / self.eligible_count if self.eligible_count else 0.0


class ScoringCoverageError(RuntimeError):
    """Raised when a Daily window cannot support relevance-ranked publication."""

    def __init__(
        self,
        *,
        eligible_count: int,
        scored_count: int,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        self.eligible_count = eligible_count
        self.scored_count = scored_count
        self.coverage = scored_count / eligible_count if eligible_count else 0.0
        self.window_start = window_start
        self.window_end = window_end
        super().__init__(
            "Daily scoring coverage insufficient: "
            f"{scored_count}/{eligible_count} ({self.coverage:.1%})"
        )


def current_brief_window(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    """Return the rolling 24h brief window in UTC-naive datetimes."""
    utc_end = now or datetime.utcnow()
    utc_start = utc_end - timedelta(hours=BRIEF_WINDOW_HOURS)
    return utc_start.replace(tzinfo=None), utc_end.replace(tzinfo=None), "rolling_24h"


def window_end_for_archive_date(value: date | str) -> datetime:
    """Return the UTC-naive daily window end for a Beijing archive date."""

    archive_date = date.fromisoformat(value) if isinstance(value, str) else value
    return datetime.combine(archive_date, time.min)


def _clean_model_output(text: str) -> str | None:
    cleaned = text.strip()
    return cleaned or None


def _article_timestamp(article: Article) -> datetime:
    return article.published_at or article.collected_at


def _normalize_title(title: str | None) -> str:
    normalized = re.sub(r"\s+", " ", (title or "").strip().lower())
    normalized = re.sub(r"\s+-\s+[^-]{2,40}$", "", normalized)
    return normalized


def _article_dedup_key(article: Article) -> str:
    title_key = _normalize_title(article.title)
    if len(title_key) >= 12:
        return f"title:{title_key}"
    return f"url:{(article.url or article.source_id or title_key).strip().lower()}"


def _is_publishable_article(article: Article, window_start: datetime, window_end: datetime) -> bool:
    article_time = _article_timestamp(article)
    if not (window_start <= article_time < window_end):
        return False

    title = article.title or ""
    if not title.strip():
        return False
    return not any(pattern.search(title) for pattern in _NOISE_TITLE_PATTERNS)


def _has_valid_relevance_score(article: Article) -> bool:
    return article.relevance_score is not None and 1 <= article.relevance_score <= 5


def _article_rank(article: Article) -> tuple[int, datetime]:
    if not _has_valid_relevance_score(article):
        raise ValueError("Cannot relevance-rank an article without a valid score")
    return (article.relevance_score, _article_timestamp(article))


def _select_articles_with_coverage(
    articles: list[Article],
    window_start: datetime,
    window_end: datetime,
    limit: int,
) -> ArticleSelection:
    eligible_by_key: dict[str, list[Article]] = {}
    for article in articles:
        if _is_publishable_article(article, window_start, window_end):
            eligible_by_key.setdefault(_article_dedup_key(article), []).append(article)

    scored: list[Article] = []
    for duplicates in eligible_by_key.values():
        valid = [article for article in duplicates if _has_valid_relevance_score(article)]
        if valid:
            scored.append(max(valid, key=_article_rank))

    ranked = sorted(scored, key=_article_rank, reverse=True)
    return ArticleSelection(
        articles=ranked[:limit],
        eligible_count=len(eligible_by_key),
        scored_count=len(scored),
    )


def _select_publishable_articles(
    articles: list[Article],
    window_start: datetime,
    window_end: datetime,
    limit: int,
) -> list[Article]:
    return _select_articles_with_coverage(articles, window_start, window_end, limit).articles


def _source_health_summary(session, window_start: datetime, window_end: datetime) -> str:
    """Build user-facing source health context for the LLM prompt."""
    from sqlalchemy import func
    from sources.registry import list_all_sources, list_active_sources

    configured = list_all_sources(session)
    active = list_active_sources(session)
    configured_types = {s.source_type for s in configured}
    active_types = {s.source_type for s in active}

    fresh_types = {
        row[0]
        for row in (
            session.query(Article.source, func.count(Article.id))
            .filter(Article.collected_at >= window_start)
            .filter(Article.collected_at < window_end)
            .filter(Article.collection_lane == "hourly")
            .group_by(Article.source)
            .all()
        )
    }

    issues: list[str] = []
    for source_type, impact in [
        ("xueqiu", "A股情绪/KOL确认不足"),
        ("social_kol", "全球KOL一手观点覆盖不足"),
    ]:
        if source_type in configured_types and source_type not in active_types:
            issues.append(f"- {SOURCE_LABELS[source_type]}：当前未启用，{impact}。")

    for source_type, impact in [
        ("website_monitor", "产品发布/政策原文确认偏弱"),
        ("xueqiu", "A股情绪确认偏弱"),
        ("social_kol", "全球KOL观点确认偏弱"),
    ]:
        if source_type in active_types and source_type not in fresh_types:
            issues.append(f"- {SOURCE_LABELS[source_type]}：过去24小时无新增可用内容，{impact}。")

    if issues:
        return "\n".join(issues)
    return "- 核心财经、新闻、社区、开发者与A股社交来源在本窗口有新增；无关键覆盖缺口。"


def _deepseek_api_key() -> str | None:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key

    key_path = Path(
        os.getenv("DEEPSEEK_API_KEY_FILE", str(DEFAULT_DEEPSEEK_API_KEY_FILE))
    ).expanduser()
    try:
        secret_text = key_path.read_text(encoding="utf-8")
    except OSError:
        logger.error("DeepSeek API key is not configured")
        return None

    match = re.search(r"(?:DEEPSEEK_API_KEY\s*[=:]\s*)?(sk-[A-Za-z0-9_-]+)", secret_text)
    if not match:
        logger.error("DeepSeek API key is not configured")
        return None
    return match.group(1)


def _call_codex(prompt: str) -> tuple[str | None, str | None]:
    """Run one isolated, read-only Codex fallback attempt."""

    global _last_codex_failure
    _last_codex_failure = "not_attempted"
    try:
        content = CodexCLIClient().complete(
            prompt,
            system_prompt=CODEX_FALLBACK_PREFIX,
            timeout=CODEX_TIMEOUT_SECONDS,
            max_tokens=6000,
        )
    except CodexCLIError as exc:
        _last_codex_failure = exc.reason
        logger.error("Codex CLI fallback failed: %s", exc.reason)
        return None, None
    else:
        _last_codex_failure = "ok"
        return content, "codex-cli"


def _call_deepseek(prompt: str) -> tuple[str | None, str | None]:
    global _last_deepseek_failure
    _last_deepseek_failure = "not_attempted"
    key = _deepseek_api_key()
    if not key:
        _last_deepseek_failure = "key_missing"
        return None, None

    requested_model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip()
    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": requested_model,
                "messages": [{"role": "user", "content": prompt}],
                "thinking": {"type": "disabled"},
                "temperature": 0.2,
                "max_tokens": 6000,
            },
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        content = _clean_model_output(data["choices"][0]["message"]["content"])
        if not content:
            _last_deepseek_failure = "empty_response"
            logger.error("DeepSeek API returned an empty response")
            return None, None
        _last_deepseek_failure = "ok"
        return content, str(data.get("model") or requested_model)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        _last_deepseek_failure = f"http_{status}" if status else "http_error"
        logger.error("DeepSeek API request failed: %s", _last_deepseek_failure)
        return None, None
    except requests.Timeout:
        _last_deepseek_failure = "timeout"
        logger.exception("DeepSeek API request timed out")
        return None, None
    except requests.RequestException:
        _last_deepseek_failure = "transport_error"
        logger.exception("DeepSeek API request failed")
        return None, None
    except (KeyError, IndexError, TypeError, ValueError):
        _last_deepseek_failure = "invalid_response"
        logger.exception("DeepSeek API request failed")
        return None, None


def _call_llm(prompt: str) -> tuple[str | None, str | None]:
    """Generate with DeepSeek first, then one audited Codex CLI fallback."""

    global _last_codex_failure
    _last_codex_failure = "not_attempted"
    content, model = _call_deepseek(prompt)
    if content:
        logger.info("Brief generated with DeepSeek model %s", model)
        return content, f"deepseek:{model}"
    deepseek_failure = _last_deepseek_failure
    content, provider = _call_codex(prompt)
    if content:
        logger.info("Brief generated with Codex CLI fallback after DeepSeek failure (%s)", deepseek_failure)
        return content, provider
    logger.error(
        "Both DeepSeek and Codex CLI failed; delivery must be skipped (deepseek=%s, codex=%s)",
        deepseek_failure,
        _last_codex_failure,
    )
    return None, None


def _build_prompt(
    articles: list[Article],
    events: list[Event],
    window_start: datetime,
    window_end: datetime,
    slot: str,
    source_health: str,
) -> str:
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d %H:%M UTC")
    window_text = (
        f"{window_start.strftime('%Y-%m-%d %H:%M UTC')} - "
        f"{window_end.strftime('%Y-%m-%d %H:%M UTC')} (past 24h)"
    )

    # Format articles
    articles_text = ""
    for i, a in enumerate(articles[:80], 1):
        title = (a.title or "").strip()[:100]
        source = SOURCE_LABELS.get(a.source, "公开来源")
        content_snippet = (a.content or "")[:150].strip()
        article_time = _article_timestamp(a).strftime("%Y-%m-%d %H:%M UTC")
        articles_text += f"{i}. [{source}] {title} ({article_time})"
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

    return f"""你是一位资深交易分析师和交易产品 PM，给活跃交易者写 Daily Trader Brief。Ticker、专业术语保留英文。

当前时间: {date_str}
覆盖窗口: {window_text}

跨源验证事件:
{events_text}

来源健康:
{source_health}

最近文章 ({len(articles)} 篇):
{articles_text}

请严格按照以下用户可读格式输出，不要输出内部字段:

🎯 Daily Trader Brief — {date_str}
覆盖窗口：{window_text}

## 今日交易地图
- [主题]：方向 [偏多/偏空/观望]；相关标的 [ticker/行业]；置信度 [高/中/低]；一句话交易含义。

## 过去24小时发生了什么
1. **[一句话标题]** | [高/中/低] 确信度 | [时间框架]
   → [相关 ticker/行业]: [发生了什么、为什么重要]
   → 交易含义: [今天应该关注/规避/等待什么]
   → 证据性质: [已发生事实/公司公告/价格动作/观点/预测]

## A股映射
- [全球或宏观事件] → [A股行业/概念/个股]：为什么相关，今天看什么确认信号。

## 今天不该追的东西
- [低质量/旧闻/已反应/仅观点]：为什么降权。

⚡️ 跨叙事关联
• [跨主题关联分析1]
• [跨主题关联分析2]

## Source Health
- [一句话说明覆盖是否完整；必须说明会影响交易判断的信息缺口]

硬性要求：
- 具体到 ticker、行业、价格、百分比；A股/港股内容用中文，美股/全球内容也用中文描述但 ticker 保留英文。
- 不要写“分析了多少篇文章”“数据源: rss/google_news/reddit”“score”“tags”“narrative_tags”“signal ratio”等内部信息。
- 不要重复同一条新闻；同一事件只出现一次。
- 如果只是旧闻、观点文、预测、直播标题、无描述项目，只能放进“今天不该追的东西”，不能作为主信号。
- 每个主要结论都必须说明交易含义，不能只做新闻摘要。
- Source Health 只写用户能理解的覆盖缺口，例如“A股社交/KOL源未启用”；不要输出源表、字段名或内部 source id。

重要价格规则：必须区分“当前价格/已发生事实”和“目标价/情景价/分析师预测”。如果文章只是 price target、scenario、forecast，不得写成“已经突破”。published_at 明显早于本窗口的旧文章不得作为今日事实。"""


def generate_brief(
    limit: int = 100,
    *,
    window_end: datetime | None = None,
    publish_current: bool = True,
) -> int | None:
    """Generate a brief for a current or explicit historical 24-hour window."""
    init_db()
    session = get_session()

    try:
        now = window_end or datetime.utcnow()
        window_start, window_end, slot = current_brief_window(now)

        # Get only the active fixed-window batch. Guard against stale rediscovery:
        # if a source re-collects an old article today, published_at must still
        # be inside the active window unless the source does not provide it.
        candidates = (
            session.query(Article)
            .filter(Article.collected_at >= window_start)
            .filter(Article.collected_at < window_end)
            .filter(Article.collection_lane == "hourly")
            .filter((Article.published_at.is_(None)) | (Article.published_at >= window_start))
            .filter((Article.published_at.is_(None)) | (Article.published_at < window_end))
            .order_by(Article.collected_at.desc())
            .limit(max(limit * 3, 300))
            .all()
        )
        selection = _select_articles_with_coverage(candidates, window_start, window_end, limit)
        articles = selection.articles

        if selection.scored_count < selection.eligible_count:
            raise ScoringCoverageError(
                eligible_count=selection.eligible_count,
                scored_count=selection.scored_count,
                window_start=window_start,
                window_end=window_end,
            )

        if len(articles) < 5:
            logger.warning(
                "Only %d fresh articles in %s window %s - %s, skipping brief",
                len(articles), slot, window_start, window_end,
            )
            return None

        # Use only events created inside the fixed brief window. The event
        # refresher can touch old active rows, so updated_at alone lets stale
        # summaries leak into today's published brief.
        events = (
            session.query(Event)
            .filter(Event.status == "active", Event.source_count >= 2)
            .filter(Event.created_at >= window_start)
            .filter(Event.created_at < window_end)
            .order_by(Event.signal_score.desc())
            .limit(10)
            .all()
        )

        source_health = _source_health_summary(session, window_start, window_end)
        prompt = _build_prompt(articles, events, window_start, window_end, slot, source_health)
        logger.info(
            "Generating %s brief from %d fresh articles, %d events (%s - %s)...",
            slot, len(articles), len(events), window_start, window_end,
        )

        content, provider = _call_llm(prompt)
        if not content:
            logger.error("Failed to generate brief")
            return None

        validation = validate_published_brief(content)
        if not validation.passed:
            rejected = Brief(
                content=content,
                article_count=len(articles),
                signal_count=0,
                status="rejected",
                provider=provider,
                candidate_article_count=selection.eligible_count,
                scored_article_count=selection.scored_count,
                scoring_coverage=selection.coverage,
                created_at=now,
            )
            session.add(rejected)
            session.commit()
            logger.error("Rejected brief #%d: %s", rejected.id, "; ".join(validation.issues))
            return None

        # Count signals (lines with conviction markers)
        signal_count = content.count("| H |") + content.count("| M |") + content.count("| L |")
        signal_count += content.count("Conviction: H") + content.count("Conviction: M") + content.count("Conviction: L")
        signal_count += len(re.findall(r"^\s*\d+[.)、]", content, flags=re.MULTILINE))

        if publish_current:
            # A successful current batch replaces the previously published
            # user-facing brief. Historical backfills stay archived.
            session.query(Brief).filter(Brief.status == "published").update(
                {"status": "archived"},
                synchronize_session=False,
            )

        brief = Brief(
            content=content,
            article_count=len(articles),
            signal_count=max(signal_count, 1),
            status="published" if publish_current else "archived",
            provider=provider,
            candidate_article_count=selection.eligible_count,
            scored_article_count=selection.scored_count,
            scoring_coverage=selection.coverage,
            created_at=now,
        )
        session.add(brief)
        session.commit()

        logger.info(
            "Brief #%d generated by %s: %d chars, %d signals",
            brief.id, provider, len(content), brief.signal_count,
        )
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
