#!/usr/bin/env python3
"""CLI to run park-intel collectors."""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from collectors.social_kol import SocialKolCollector
from collectors.github_release import GitHubReleaseCollector
from collectors.github_trending import GitHubTrendingCollector
from collectors.google_news import GoogleNewsCollector
from collectors.hackernews import HackerNewsCollector
from collectors.reddit import RedditCollector
from collectors.rss import RSSCollector
from collectors.webpage_monitor import WebpageMonitorCollector
from collectors.xueqiu import XueqiuCollector
from collectors.yahoo_finance import YahooFinanceCollector
from collectors.realtime_news import CLSRealtimeCollector, EastmoneyRealtimeCollector

REALTIME_COLLECTOR_SOURCES = config.REALTIME_SOURCE_TYPES

COLLECTORS: dict[str, type] = {
    "hackernews": HackerNewsCollector,
    "xueqiu": XueqiuCollector,
    "rss": RSSCollector,
    "github_trending": GitHubTrendingCollector,
    "yahoo_finance": YahooFinanceCollector,
    "google_news": GoogleNewsCollector,
    "social_kol": SocialKolCollector,
    "reddit": RedditCollector,
    "github_release": GitHubReleaseCollector,
    "website_monitor": WebpageMonitorCollector,
    "cls_telegraph": CLSRealtimeCollector,
    "eastmoney_global_news": EastmoneyRealtimeCollector,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run park-intel collectors")
    parser.add_argument(
        "--source",
        choices=list(COLLECTORS.keys()),
        help="Run a specific collector (default: all)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    sources = [args.source] if args.source else list(COLLECTORS.keys())

    if not config.realtime_lane_enabled():
        sources = [source for source in sources if source not in REALTIME_COLLECTOR_SOURCES]
        if args.source in REALTIME_COLLECTOR_SOURCES:
            logging.warning(
                "Realtime source %s is disabled; set REALTIME_LANE_ENABLED=1 after operator review",
                args.source,
            )

    total_saved = 0
    for source in sources:
        collector_cls = COLLECTORS[source]
        logging.info("Running collector: %s", source)
        try:
            collector = collector_cls()
            saved = collector.run()
            total_saved += saved
        except Exception:
            logging.exception("Collector %s failed", source)

    logging.info("Done. Total new articles saved: %d", total_saved)


if __name__ == "__main__":
    main()
