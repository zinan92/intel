"""Quality gates for user-facing trader briefs."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class BriefValidation:
    passed: bool
    issues: list[str]


_INTERNAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\[score\s*=", re.I), "contains internal score annotations"),
    (re.compile(r"\bscore\s*[>=≥]\s*\d", re.I), "contains internal score thresholds"),
    (re.compile(r"\bnarrative\s*:", re.I), "contains internal narrative field labels"),
    (re.compile(r"\btags\s*:", re.I), "contains internal tag field labels"),
    (re.compile(r"\bsource_count\b|\barticle_count\b", re.I), "contains database field names"),
    (re.compile(r"数据源\s*[:：]"), "contains source plumbing footer"),
    (re.compile(r"信号比\s*[:：]"), "contains internal signal ratio"),
    (re.compile(r"分析\s*\d+\s*篇文章"), "contains article-count boilerplate"),
    (re.compile(r"\bgithub_trending\b|\bgoogle_news\b|\byahoo_finance\b", re.I), "contains raw source identifiers"),
    (re.compile(r"\brolling_24h\b", re.I), "contains internal window identifier"),
]

_STALE_GOLD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"黄金|gold|xau", re.I),
    re.compile(r"5,?000"),
    re.compile(r"record\s+high|历史新高|突破", re.I),
]


def _numbered_titles(content: str) -> list[str]:
    titles: list[str] = []
    for line in content.splitlines():
        match = re.match(r"\s*\d+[.)、]\s*(?:\*\*)?(.+?)(?:\*\*)?\s*(?:\||$)", line)
        if match:
            title = re.sub(r"\s+", " ", match.group(1)).strip().lower()
            if title:
                titles.append(title)
    return titles


def validate_published_brief(content: str) -> BriefValidation:
    """Validate that a generated brief is safe to publish to traders."""
    issues: list[str] = []
    stripped = content.strip()

    if len(stripped) < 500:
        issues.append("brief is too short to be useful")

    for pattern, issue in _INTERNAL_PATTERNS:
        if pattern.search(stripped):
            issues.append(issue)

    titles = _numbered_titles(stripped)
    duplicates = [title for title, count in Counter(titles).items() if count > 1]
    if duplicates:
        issues.append(f"duplicate numbered insight titles: {', '.join(duplicates[:3])}")

    if all(pattern.search(stripped) for pattern in _STALE_GOLD_PATTERNS):
        issues.append("gold appears to be described as a $5,000 breakout/record fact")

    required_sections = [
        (re.compile(r"今日交易地图"), "今日交易地图"),
        (re.compile(r"过去\s*24\s*小时"), "过去24小时"),
        (re.compile(r"交易含义"), "交易含义"),
        (re.compile(r"Source Health"), "Source Health"),
    ]
    missing = [label for pattern, label in required_sections if not pattern.search(stripped)]
    if missing:
        issues.append(f"missing trader-facing sections: {', '.join(missing)}")

    return BriefValidation(passed=not issues, issues=issues)
