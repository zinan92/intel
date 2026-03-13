#!/usr/bin/env python3
"""Narrative 趋势追踪 - 分析过去7天 narrative tags 的升温/降温趋势."""

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "park_intel.db"


def get_narrative_counts(db_path: Path, days: int = 7) -> dict[str, dict[str, int]]:
    """Return {tag: {date_str: count}} for the past N days."""
    conn = sqlite3.connect(db_path)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT narrative_tags, date(published_at) as d FROM articles "
        "WHERE narrative_tags IS NOT NULL AND narrative_tags != '[]' "
        "AND published_at >= ?",
        (cutoff,),
    ).fetchall()
    conn.close()

    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for tags_json, day in rows:
        try:
            tags = json.loads(tags_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for tag in tags:
            if tag and tag.strip():
                counts[tag.strip()][day] += 1
    return counts


def analyze_trends(counts: dict[str, dict[str, int]]) -> dict[str, list[tuple[str, float, int, int]]]:
    """Split tags into heating/cooling/stable based on recent 3d vs prior 4d."""
    today = datetime.now().date()
    recent_days = {(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)}
    prior_days = {(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3, 7)}

    heating, cooling, stable = [], [], []

    noise_keywords = {"noise", "unrelated", "non-market", "empty-repo", "personal", "student"}

    for tag, daily in counts.items():
        # Skip noise tags
        if any(kw in tag.lower() for kw in noise_keywords):
            continue
        recent = sum(v for d, v in daily.items() if d in recent_days)
        prior = sum(v for d, v in daily.items() if d in prior_days)
        total = recent + prior

        if total < 2:  # skip noise
            continue

        if prior == 0:
            if recent >= 2:
                heating.append((tag, float("inf"), recent, prior))
            continue

        change = (recent - prior) / prior
        bucket = heating if change > 0.5 else (cooling if change < -0.5 else stable)
        bucket.append((tag, change, recent, prior))

    # Sort: heating by change desc, cooling by change asc, stable by total desc
    heating.sort(key=lambda x: (-x[2] if x[1] == float("inf") else -x[1]))
    cooling.sort(key=lambda x: x[1])
    stable.sort(key=lambda x: -(x[2] + x[3]))

    return {"heating": heating, "cooling": cooling, "stable": stable}


def format_report(trends: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"📈 Narrative 趋势报告 ({today})", ""]

    def fmt(items, emoji, label):
        lines.append(f"{emoji} {label}")
        if not items:
            lines.append("  （无）")
        for tag, change, recent, prior in items:
            pct = "🆕" if change == float("inf") else f"{change:+.0%}"
            lines.append(f"  • {tag}  {pct}  (近3d:{recent} / 前4d:{prior})")
        lines.append("")

    fmt(trends["heating"], "🔥", "升温 Narratives（>50%）")
    fmt(trends["cooling"], "❄️", "降温 Narratives（<-50%）")
    fmt(trends["stable"], "📊", "稳定 Narratives（±50%内）")

    return "\n".join(lines)


def main():
    counts = get_narrative_counts(DB_PATH)
    trends = analyze_trends(counts)
    report = format_report(trends)
    print(report)
    return report


if __name__ == "__main__":
    main()
