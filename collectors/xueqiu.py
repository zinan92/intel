"""Xueqiu (雪球) collector — hot timeline + KOL feeds.

Timeline API (public_timeline_by_category) works with plain requests + cookie.
User timeline API is behind Alibaba Cloud WAF → requires Playwright stealth.
"""

import html
import json
import logging
import re
import time
from datetime import datetime
from typing import Any

import requests

from collectors.base import BaseCollector
from config import XUEQIU_COOKIE, XUEQIU_KOL_IDS

logger = logging.getLogger(__name__)

_BASE_URL = "https://xueqiu.com"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "application/json",
    "Referer": "https://xueqiu.com/",
}

# Category IDs for public_timeline_by_category
_CATEGORIES = {
    "hot": 111,      # 热门
    "stocks": 114,   # 股票
}


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _ms_to_datetime(ms: int | None) -> datetime | None:
    """Convert millisecond timestamp to datetime."""
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000)
    except (ValueError, OSError):
        return None


def _parse_cookies(cookie_str: str) -> list[dict]:
    """Parse cookie string into Playwright cookie dicts."""
    cookies = []
    for part in cookie_str.split("; "):
        if "=" in part:
            k, v = part.split("=", 1)
            cookies.append({
                "name": k.strip(),
                "value": v.strip(),
                "domain": ".xueqiu.com",
                "path": "/",
            })
    return cookies


class XueqiuCollector(BaseCollector):
    """Collect posts from Xueqiu (雪球)."""

    source = "xueqiu"

    def __init__(self) -> None:
        super().__init__()
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        if XUEQIU_COOKIE:
            self._session.headers["Cookie"] = XUEQIU_COOKIE
        else:
            try:
                self._session.get(_BASE_URL, timeout=10)
            except requests.RequestException:
                logger.warning("Failed to initialize Xueqiu session")

    # ------------------------------------------------------------------
    # Timeline (requests — no WAF issues)
    # ------------------------------------------------------------------

    def _fetch_timeline(self, category_id: int, count: int = 20) -> list[dict[str, Any]]:
        """Fetch public timeline by category."""
        url = f"{_BASE_URL}/v4/statuses/public_timeline_by_category.json"
        params = {"since_id": -1, "max_id": -1, "count": count, "category": category_id}

        try:
            resp = self._session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error("Xueqiu timeline request failed: %s", e)
            return []
        except ValueError:
            logger.error("Xueqiu timeline returned non-JSON response")
            return []

        articles: list[dict[str, Any]] = []
        for item in data.get("list", []):
            # Timeline wraps status in a JSON string under "data"
            raw_data = item.get("data")
            if isinstance(raw_data, str):
                try:
                    status = json.loads(raw_data)
                except (json.JSONDecodeError, TypeError):
                    continue
            elif isinstance(raw_data, dict):
                status = raw_data
            else:
                status = item  # fallback

            article = self._parse_status(status)
            if article:
                articles.append(article)

        return articles

    # ------------------------------------------------------------------
    # KOL user timeline (Playwright stealth — WAF bypass)
    # ------------------------------------------------------------------

    def _fetch_kol_timelines_playwright(
        self, kols: list[dict[str, str]], count: int = 10
    ) -> list[dict[str, Any]]:
        """Fetch multiple KOL timelines using Playwright stealth to bypass Alibaba Cloud WAF.

        Strategy: load user page in browser context first (solves WAF JS challenge),
        then use page.evaluate(fetch(...)) to call the API from within the browser
        context where cookies/WAF tokens are already set.
        """
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
        except ImportError:
            logger.error(
                "playwright / playwright-stealth not installed. "
                "Run: pip install playwright playwright-stealth && playwright install chromium"
            )
            return []

        all_articles: list[dict[str, Any]] = []
        stealth = Stealth()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=_USER_AGENT)

                if XUEQIU_COOKIE:
                    ctx.add_cookies(_parse_cookies(XUEQIU_COOKIE))

                page = ctx.new_page()
                stealth.apply_stealth_sync(page)

                # Load homepage first to pass WAF JS challenge
                logger.info("Loading Xueqiu homepage for WAF init...")
                page.goto(f"{_BASE_URL}/", timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)

                for kol in kols:
                    kol_id, kol_name, kol_tag = kol["id"], kol["name"], kol["tag"]
                    logger.info("Fetching Xueqiu KOL %s (%s) via Playwright in-page fetch", kol_name, kol_id)

                    api_url = (
                        f"{_BASE_URL}/v4/statuses/user_timeline.json"
                        f"?user_id={kol_id}&page=1&count={count}"
                    )
                    try:
                        # Use in-page fetch to call API with WAF cookies already present
                        data = page.evaluate(
                            """async (url) => {
                                const resp = await fetch(url);
                                if (!resp.ok) return {error: resp.status};
                                return await resp.json();
                            }""",
                            api_url,
                        )
                        if not data or "error" in data:
                            # Fallback: navigate to user page first, then fetch
                            logger.info("In-page fetch failed, trying user page load for %s", kol_name)
                            page.goto(f"{_BASE_URL}/u/{kol_id}", timeout=20000, wait_until="domcontentloaded")
                            page.wait_for_timeout(3000)
                            data = page.evaluate(
                                """async (url) => {
                                    const resp = await fetch(url);
                                    if (!resp.ok) return {error: resp.status};
                                    return await resp.json();
                                }""",
                                api_url,
                            )
                    except Exception as e:
                        logger.error("Playwright fetch failed for KOL %s: %s", kol_name, e)
                        continue

                    if not data or "error" in data:
                        logger.error("No data for KOL %s, got: %s", kol_name, data)
                        continue

                    statuses = data.get("statuses", data.get("list", []))
                    for item in statuses:
                        article = self._parse_status(item)
                        if article:
                            if kol_tag and kol_tag not in article["tags"]:
                                article["tags"].append(kol_tag)
                            all_articles.append(article)

                    logger.info("Got %d posts from KOL %s", len(statuses), kol_name)
                    time.sleep(1)  # Be polite

                browser.close()

        except Exception as e:
            logger.error("Playwright session failed: %s", e)

        return all_articles

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_status(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a Xueqiu status into an article dict."""
        post_id = item.get("id")
        if not post_id:
            return None

        user = item.get("user", {}) or {}
        author = user.get("screen_name", "")

        # Content: prefer "text", fall back to "description"
        text = item.get("text", "") or item.get("description", "") or ""
        text = _strip_html(text)

        if not text:
            return None

        title = item.get("title") or ""
        if not title:
            title = text[:100]

        # Build URL
        user_id = user.get("id", "") or item.get("user_id", "")
        url = f"https://xueqiu.com/{user_id}/{post_id}" if user_id else f"https://xueqiu.com/0/{post_id}"

        return {
            "source": self.source,
            "source_id": f"xueqiu_{post_id}",
            "author": author,
            "title": title,
            "content": text,
            "url": url,
            "tags": [],
            "score": item.get("reply_count", 0) or 0,
            "published_at": _ms_to_datetime(item.get("created_at")),
        }

    # ------------------------------------------------------------------
    # Main collect
    # ------------------------------------------------------------------

    def collect(self) -> list[dict[str, Any]]:
        """Collect from hot timelines + KOL feeds."""
        if not XUEQIU_COOKIE:
            logger.warning("[%s] Skipping collection: XUEQIU_COOKIE not configured", self.source)
            return []

        all_articles: list[dict[str, Any]] = []

        # 1. Hot timelines (requests — fast, no WAF)
        for name, cat_id in _CATEGORIES.items():
            logger.info("Fetching Xueqiu %s timeline", name)
            articles = self._fetch_timeline(cat_id)
            all_articles.extend(articles)
            logger.info("Got %d posts from Xueqiu %s", len(articles), name)
            time.sleep(1)

        # 2. KOL feeds (Playwright stealth — WAF bypass)
        if XUEQIU_KOL_IDS:
            kol_articles = self._fetch_kol_timelines_playwright(XUEQIU_KOL_IDS)
            all_articles.extend(kol_articles)

        return all_articles
