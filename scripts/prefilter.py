#!/usr/bin/env python3
"""Pre-filter articles for LLM scoring.

Reduces daily noise (13k+ → ~1-2k) by:
1. Dedup by title (or content hash for titleless sources like twitter)
2. Remove empty/ultra-short content (<30 chars)
3. Keep only the latest entry per unique title
4. Mark filtered articles in a new table for tagger pickup

Usage:
    python3 scripts/prefilter.py              # filter last 12h
    python3 scripts/prefilter.py --hours 24   # filter last 24h
    python3 scripts/prefilter.py --dry-run    # just show stats
"""

import argparse
import hashlib
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from db.database import get_session, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Minimum content length to keep
MIN_CONTENT_LEN = 30

# GitHub-specific prefilter settings
GITHUB_KEYWORD_WHITELIST = [
    "trading", "quant", "agent", "claude", "openclaw",
]
GITHUB_MIN_STARS = 100


def ensure_prefilter_table(session):
    """Create prefiltered_articles table if it doesn't exist."""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS prefiltered_articles (
            id INTEGER PRIMARY KEY,
            article_id INTEGER NOT NULL UNIQUE,
            dedup_key TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (article_id) REFERENCES articles(id)
        )
    """))
    session.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_prefiltered_created 
        ON prefiltered_articles(created_at)
    """))
    session.commit()


def _should_skip_github(title: str, content: str) -> str | None:
    """Return skip reason if a GitHub article should be filtered, else None."""
    title_lower = (title or "").lower()
    content_str = content or ""

    # Fork repos
    if "fork of" in title_lower:
        return "github_fork"

    # No description or short description (<10 chars)
    first_line = content_str.split("\n")[0].strip() if content_str else ""
    if not first_line or "No description available" in first_line or len(first_line) < 10:
        return "github_no_desc"

    # Star check: skip if stars < threshold, unless title has whitelisted keyword
    has_keyword = any(kw in title_lower for kw in GITHUB_KEYWORD_WHITELIST)
    star_match = re.search(r"⭐ Stars: (\d+)", content_str)
    stars = int(star_match.group(1)) if star_match else 0
    if stars < GITHUB_MIN_STARS and not has_keyword:
        return "github_low_stars"

    return None


def dedup_key(title, content, source):
    """Generate dedup key: title if available, else content hash."""
    if title and len(title.strip()) > 5:
        return f"{source}:{title.strip().lower()}"
    # For titleless sources (twitter etc), hash first 200 chars of content
    snippet = (content or "")[:200].strip().lower()
    return f"{source}:hash:{hashlib.md5(snippet.encode()).hexdigest()}"


def run_prefilter(hours: int = 12, dry_run: bool = False):
    init_db()
    session = get_session()
    ensure_prefilter_table(session)

    # Get articles from the time window that haven't been prefiltered yet
    rows = session.execute(text("""
        SELECT a.id, a.source, a.title, a.content, a.collected_at
        FROM articles a
        LEFT JOIN prefiltered_articles p ON a.id = p.article_id
        WHERE a.collected_at >= datetime('now', :hours_ago)
          AND p.id IS NULL
        ORDER BY a.collected_at DESC
    """), {"hours_ago": f"-{hours} hours"}).fetchall()

    logger.info("Found %d unprocessed articles in last %dh", len(rows), hours)

    if not rows:
        return

    # Dedup: keep latest per dedup_key
    seen = {}  # dedup_key -> (article_id, source)
    skipped_short = 0
    skipped_dup = 0
    skipped_github = {"github_fork": 0, "github_no_desc": 0, "github_low_stars": 0}

    for row in rows:
        aid, source, title, content, collected_at = row

        # Skip empty/ultra-short
        if not content or len(content.strip()) < MIN_CONTENT_LEN:
            skipped_short += 1
            continue

        # GitHub-specific quality filter
        if source == "github":
            skip_reason = _should_skip_github(title, content)
            if skip_reason:
                skipped_github[skip_reason] = skipped_github.get(skip_reason, 0) + 1
                continue

        key = dedup_key(title, content, source)
        if key in seen:
            skipped_dup += 1
            continue

        seen[key] = (aid, source)

    total_github_skipped = sum(skipped_github.values())
    logger.info(
        "After filter: %d kept, %d skipped (short), %d skipped (dup), %d skipped (github quality)",
        len(seen), skipped_short, skipped_dup, total_github_skipped,
    )
    if total_github_skipped:
        for reason, cnt in sorted(skipped_github.items()):
            if cnt:
                logger.info("  GitHub filter — %s: %d", reason, cnt)

    # Stats by source
    source_counts = {}
    for aid, source in seen.values():
        source_counts[source] = source_counts.get(source, 0) + 1
    for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
        logger.info("  %s: %d articles", src, cnt)

    if dry_run:
        logger.info("Dry run — not writing to DB")
        return

    # Insert into prefiltered_articles
    inserted = 0
    for key, (aid, source) in seen.items():
        try:
            session.execute(text("""
                INSERT OR IGNORE INTO prefiltered_articles (article_id, dedup_key, source)
                VALUES (:aid, :key, :source)
            """), {"aid": aid, "key": key, "source": source})
            inserted += 1
        except Exception as e:
            logger.warning("Failed to insert article %d: %s", aid, e)

    session.commit()
    logger.info("Inserted %d prefiltered articles", inserted)


def main():
    parser = argparse.ArgumentParser(description="Pre-filter articles for LLM scoring")
    parser.add_argument("--hours", type=int, default=12, help="Look back N hours")
    parser.add_argument("--dry-run", action="store_true", help="Show stats without writing")
    args = parser.parse_args()

    run_prefilter(hours=args.hours, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
