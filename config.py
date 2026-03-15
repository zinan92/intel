"""park-intel configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# --- Paths ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "park_intel.db"

# --- API ---
API_HOST = "127.0.0.1"
API_PORT = 8001

# --- Collector: Hacker News ---
HN_API_BASE = "https://hn.algolia.com/api/v1"
HN_MIN_SCORE: int = 20
HN_HITS_PER_PAGE: int = 50
HN_SEARCH_KEYWORDS: list[str] = ["crypto", "AI", "trading", "LLM", "agent", "Claude", "OpenAI", "semiconductor", "quant", "fintech", "robotics", "automation"]

# --- Collector: Xueqiu ---
XUEQIU_COOKIE: str = os.getenv("XUEQIU_COOKIE", "")
XUEQIU_KOL_IDS: list[dict[str, str]] = [
    {"name": "不明真相的群众", "id": "1955602780", "tag": "macro"},
    {"name": "大道无形我有型", "id": "1247347556", "tag": "value"},
    {"name": "但斌", "id": "1102105103", "tag": "value"},
    {"name": "唐朝", "id": "8290096439", "tag": "value"},
    {"name": "DAVID自由之路", "id": "5819606767", "tag": "macro"},
    {"name": "释老毛", "id": "6146070786", "tag": "value"},
    {"name": "月风_投资笔记", "id": "8833808060", "tag": "macro"},
    {"name": "盛丰衍", "id": "2533840321", "tag": "trading"},
    {"name": "梁宏", "id": "9887656769", "tag": "value"},
    {"name": "坚信价值", "id": "4206051491", "tag": "value"},
    {"name": "望京博格", "id": "4579887327", "tag": "tech"},
    {"name": "呼伦少威", "id": "3755834159", "tag": "tech"},
    {"name": "ETF拯救世界", "id": "4776750571", "tag": "tech"},
    {"name": "紫葳侍郎", "id": "2289280338", "tag": "tech"},
    {"name": "超短线投机者", "id": "4792753218", "tag": "trading"},
    {"name": "追龙头", "id": "8425285191", "tag": "trading"},
    {"name": "陈达美股投资", "id": "9598793634", "tag": "us-stock"},
    {"name": "Ricky", "id": "6654628252", "tag": "us-stock"},
    {"name": "美股研究社", "id": "3582153332", "tag": "us-stock"},
    {"name": "仓又加错-刘成岗", "id": "1434679955", "tag": "us-stock"},
]

# --- Collector: Yahoo Finance ---
YAHOO_TICKERS: list[str] = [
    "GC=F",   # Gold Futures
    "GLD",    # SPDR Gold Shares ETF
    "IAU",    # iShares Gold Trust
    "NEM",    # Newmont (largest gold miner)
    "GOLD",   # Barrick Gold
]
YAHOO_SEARCH_KEYWORDS: list[str] = [
    "gold price",
    "XAUUSD",
    "gold futures",
    "federal reserve gold",
    "central bank gold reserves",
]

# --- Collector: Google News ---
GOOGLE_NEWS_QUERIES: list[dict[str, str]] = [
    {"query": "gold price forecast", "hl": "en-US", "gl": "US"},
    {"query": "XAUUSD trading", "hl": "en-US", "gl": "US"},
    {"query": "gold market analysis", "hl": "en-US", "gl": "US"},
    {"query": "federal reserve interest rate gold", "hl": "en-US", "gl": "US"},
    {"query": "central bank gold reserves", "hl": "en-US", "gl": "US"},
    {"query": "黄金价格走势", "hl": "zh-CN", "gl": "CN"},
    {"query": "黄金投资分析", "hl": "zh-CN", "gl": "CN"},
]

# --- LLM Tagging ---
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

# --- Source Bootstrap Data (V2: seed only) ---
# Used ONLY by sources/seed.py to populate the source_registry table on first run.
# Runtime (scheduler, health, feed) reads from the DB registry, not this list.
# To change source intervals or active state, edit the registry via the service layer.
SOURCE_BOOTSTRAP: list[dict] = [
    {"source": "hackernews",       "interval_hours": 4,  "category": "frontier-tech"},
    {"source": "xueqiu",           "interval_hours": 4,  "category": "cn-finance"},
    {"source": "rss",              "interval_hours": 6,  "category": "mixed"},
    {"source": "github_trending",  "interval_hours": 12, "category": "frontier-tech"},
    {"source": "yahoo_finance",    "interval_hours": 4,  "category": "macro"},
    {"source": "google_news",      "interval_hours": 4,  "category": "macro"},
    {"source": "social_kol",       "interval_hours": 4,  "category": "mixed"},
    {"source": "reddit",           "interval_hours": 6,  "category": "mixed"},
    {"source": "github_release",   "interval_hours": 12, "category": "ai-agent"},
    {"source": "website_monitor",  "interval_hours": 6,  "category": "mixed"},
]

# --- Collector: Social KOL ---
SOCIAL_KOL_HANDLES: list[dict] = [
    {"handle": "sama",            "category": "llm"},
    {"handle": "DarioAmodei",     "category": "llm"},
    {"handle": "GregBrockman",    "category": "llm"},
    {"handle": "karpathy",        "category": "llm"},
    {"handle": "demishassabis",   "category": "llm"},
    {"handle": "ylecun",          "category": "llm"},
    {"handle": "AndrewYNg",       "category": "llm"},
    {"handle": "ClementDelangue", "category": "llm"},
    {"handle": "DrJimFan",        "category": "ai-agent"},
    {"handle": "hwchase17",       "category": "ai-agent"},
    {"handle": "rowancheung",     "category": "ai-agent"},
    {"handle": "swyx",            "category": "ai-agent"},
    {"handle": "finkd",           "category": "frontier-tech"},
    {"handle": "elonmusk",        "category": "frontier-tech"},
    {"handle": "satyanadella",    "category": "frontier-tech"},
    {"handle": "sundarpichai",    "category": "frontier-tech"},
    {"handle": "pmarca",          "category": "frontier-tech"},
    {"handle": "VitalikButerin",  "category": "crypto"},
    {"handle": "cz_binance",      "category": "crypto"},
    {"handle": "brian_armstrong", "category": "crypto"},
    {"handle": "saylor",          "category": "crypto"},
    {"handle": "WuBlockchain",    "category": "crypto"},
    {"handle": "balaji",          "category": "crypto"},
]

# --- Collector: Reddit ---
REDDIT_SUBREDDITS: list[dict] = [
    {"subreddit": "MachineLearning",  "category": "llm"},
    {"subreddit": "LocalLLaMA",       "category": "llm"},
    {"subreddit": "ChatGPT",          "category": "llm"},
    {"subreddit": "OpenAI",           "category": "llm"},
    {"subreddit": "artificial",       "category": "llm"},
    {"subreddit": "singularity",      "category": "llm"},
    {"subreddit": "Anthropic",        "category": "llm"},
    {"subreddit": "CryptoCurrency",   "category": "crypto"},
    {"subreddit": "Bitcoin",          "category": "crypto"},
    {"subreddit": "ethereum",         "category": "crypto"},
    {"subreddit": "defi",             "category": "crypto"},
    {"subreddit": "programming",      "category": "frontier-tech"},
    {"subreddit": "ExperiencedDevs",  "category": "frontier-tech"},
]

# --- Collector: GitHub Release ---
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_RELEASE_REPOS: list[dict] = [
    {"repo": "openclaw/openclaw",          "category": "ai-agent"},
    {"repo": "anthropics/claude-code",     "category": "ai-agent"},
    {"repo": "google-gemini/gemini-cli",   "category": "ai-agent"},
    {"repo": "openai/codex",               "category": "ai-agent"},
]

# --- Collector: Webpage Monitor ---
WEBPAGE_MONITORS: list[dict] = [
    {
        "name": "Anthropic Claude Blog",
        "type": "scrape",
        "url": "https://claude.com/blog/",
        "category": "llm",
    },
    {
        "name": "OpenClaw Docs",
        "type": "github_commits",
        "repo": "openclaw/openclaw",
        "path": "docs/",
        "category": "ai-agent",
    },
]

# --- Collector: RSS ---
RSS_FEEDS: list[dict] = [
    # === AI / LLM Blogs ===
    {"name": "Simon Willison",        "url": "https://simonwillison.net/atom/everything/",       "category": "llm"},
    {"name": "Lilian Weng",           "url": "https://lilianweng.github.io/index.xml",            "category": "llm"},
    {"name": "Sebastian Raschka",     "url": "https://magazine.sebastianraschka.com/feed",        "category": "llm"},
    {"name": "HuggingFace Blog",      "url": "https://huggingface.co/blog/feed.xml",              "category": "llm"},
    {"name": "OpenAI Blog",           "url": "https://openai.com/blog/rss.xml",                   "category": "llm"},
    {"name": "Google DeepMind Blog",  "url": "https://deepmind.google/blog/rss.xml",              "category": "llm"},
    {"name": "NVIDIA AI Blog",        "url": "https://blogs.nvidia.com/feed/",                    "category": "llm"},
    {"name": "Gary Marcus",           "url": "https://garymarcus.substack.com/feed",              "category": "llm"},
    {"name": "AI Snake Oil",          "url": "https://aisnakeoil.substack.com/feed",              "category": "llm"},
    {"name": "Gwern",                 "url": "https://gwern.substack.com/feed",                   "category": "llm"},
    {"name": "minimaxir",             "url": "https://minimaxir.com/index.xml",                   "category": "llm"},
    {"name": "Google AI Blog",        "url": "https://blog.google/technology/ai/rss/",            "category": "llm"},
    # === AI Newsletter ===
    {"name": "Ben's Bites",           "url": "https://www.bensbites.com/feed",                    "category": "ai-agent"},
    {"name": "The Decoder",           "url": "https://the-decoder.com/feed/",                     "category": "ai-agent"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed",             "category": "ai-agent"},
    {"name": "VentureBeat AI",        "url": "https://venturebeat.com/category/ai/feed/",         "category": "ai-agent"},
    # === Frontier Tech ===
    {"name": "Hacker News Frontpage", "url": "https://hnrss.org/frontpage",                       "category": "frontier-tech"},
    {"name": "Ars Technica",          "url": "https://feeds.arstechnica.com/arstechnica/index",   "category": "frontier-tech"},
    {"name": "Wired",                 "url": "https://www.wired.com/feed/rss",                    "category": "frontier-tech"},
    {"name": "IEEE Spectrum",         "url": "https://spectrum.ieee.org/feeds/feed.rss",          "category": "frontier-tech"},
    {"name": "ByteByteGo",            "url": "https://blog.bytebytego.com/feed",                  "category": "frontier-tech"},
    {"name": "Product Hunt",          "url": "https://www.producthunt.com/feed",                  "category": "frontier-tech"},
    {"name": "Paul Graham",           "url": "http://www.aaronsw.com/2002/feeds/pgessays.rss",    "category": "frontier-tech"},
    {"name": "Geohot",                "url": "https://geohot.github.io/blog/feed.xml",            "category": "frontier-tech"},
    {"name": "antirez",               "url": "http://antirez.com/rss",                            "category": "frontier-tech"},
    {"name": "Mitchell Hashimoto",    "url": "https://mitchellh.com/feed.xml",                    "category": "frontier-tech"},
    {"name": "Dan Abramov",           "url": "https://overreacted.io/rss.xml",                    "category": "frontier-tech"},
    {"name": "matklad",               "url": "https://matklad.github.io/feed.xml",                "category": "frontier-tech"},
    {"name": "Hillel Wayne",          "url": "https://buttondown.com/hillelwayne/rss",            "category": "frontier-tech"},
    {"name": "404 Media",             "url": "https://www.404media.co/rss",                       "category": "frontier-tech"},
    # === Crypto ===
    {"name": "CoinDesk",              "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",   "category": "crypto"},
    {"name": "The Block",             "url": "https://www.theblock.co/rss.xml",                   "category": "crypto"},
    {"name": "Decrypt",               "url": "https://decrypt.co/feed",                           "category": "crypto"},
    {"name": "Cointelegraph",         "url": "https://cointelegraph.com/rss",                     "category": "crypto"},
    {"name": "Messari",               "url": "https://messari.io/rss",                            "category": "crypto"},
    {"name": "Bankless",              "url": "https://newsletter.banklesshq.com/feed",            "category": "crypto"},
    {"name": "a16z Crypto",           "url": "https://a16zcrypto.substack.com/feed",              "category": "crypto"},
    {"name": "Vitalik Buterin",       "url": "https://vitalik.eth.limo/feed.xml",                "category": "crypto"},
    # === Former Substack feeds (merged in) ===
    {"name": "The Pomp Letter",       "url": "https://pomp.substack.com/feed",                    "category": "crypto"},
    {"name": "Doomberg",              "url": "https://doomberg.substack.com/feed",                "category": "frontier-tech"},
    {"name": "One Useful Thing",      "url": "https://www.oneusefulthing.org/feed",               "category": "llm"},
    {"name": "AI Supremacy",          "url": "https://www.ai-supremacy.com/feed",                 "category": "llm"},
    {"name": "Interconnects",         "url": "https://www.interconnects.ai/feed",                 "category": "llm"},
    {"name": "Dwarkesh Patel",        "url": "https://www.dwarkeshpatel.com/feed",                "category": "frontier-tech"},
    {"name": "SemiAnalysis",          "url": "https://semianalysis.substack.com/feed",            "category": "frontier-tech"},
    # === 中文科技 ===
    {"name": "机器之心",               "url": "https://www.jiqizhixin.com/rss",                    "category": "cn-tech"},
    {"name": "36kr",                  "url": "https://36kr.com/feed",                             "category": "cn-tech"},
    {"name": "爱范儿",                 "url": "https://www.ifanr.com/feed",                        "category": "cn-tech"},
    {"name": "少数派",                 "url": "https://sspai.com/feed",                            "category": "cn-tech"},
    {"name": "InfoQ中文",              "url": "https://www.infoq.cn/feed",                         "category": "cn-tech"},
    # === 中文财经 ===
    {"name": "华尔街见闻",             "url": "https://wallstreetcn.com/rss",                      "category": "cn-finance"},
    # === AI Platform Blogs ===
    {"name": "OpenAI Developers Blog","url": "https://developers.openai.com/rss.xml",             "category": "ai-agent"},
]
