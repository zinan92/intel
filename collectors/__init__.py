"""Collector modules — lazy-imported by scheduler.py to avoid import lock deadlock."""

__all__ = [
    "BaseCollector",
    "ClawFeedCollector",
    "GitHubReleaseCollector",
    "GitHubTrendingCollector",
    "GoogleNewsCollector",
    "HackerNewsCollector",
    "RedditCollector",
    "RSSCollector",
    "WebpageMonitorCollector",
    "XueqiuCollector",
    "YahooFinanceCollector",
]
