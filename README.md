<div align="center">

# qualitative-data-pipeline

**定性信号工作台 — 从噪音中提取市场叙事**

从 10+ 数据源采集、评分、聚合高价值内容，输出结构化信号 API

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](#)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)](#)
[![React](https://img.shields.io/badge/React_18-61DAFB?style=flat-square&logo=react&logoColor=black)](#)
[![Claude](https://img.shields.io/badge/Claude_AI-000?style=flat-square&logo=anthropic&logoColor=white)](#)

</div>

---

## 它解决什么问题

交易员每天面对海量信息：推特、雪球、HN、新闻、GitHub——分散在十几个平台，无法高效过滤。

这个系统把采集、去噪、评分、归类全部自动化，最终输出：
- **Feed API** — 按优先级排序的结构化信号流
- **Signals API** — 实时追踪话题热度和叙事动量
- **阅读工作台** — 在一个界面里消化所有源

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      数据源 (10+ Collectors)                 │
│                                                              │
│  HN · RSS · 雪球 · GitHub Trending · Yahoo Finance           │
│  Google News · Reddit · GitHub Releases · 网页监控 · ClawFeed │
└──────────────────────┬───────────────────────────────────────┘
                       │ 采集 + 去重 + 关键词标签 (13类)
                       ▼
             ┌─────────────────┐
             │  Source Registry │ ← 单一数据源真相
             │     SQLite      │
             └────────┬────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
    LLM 评分器   FastAPI APIs    调度器
    (Claude)    /api/* + /ui/*  (APScheduler)
    相关度+叙事        │
                      ▼
             React 阅读工作台
```

## 数据源

| 源 | 说明 | 采集方式 |
|---|---|---|
| **Hacker News** | 科技前沿，score ≥ 20 | Algolia API |
| **RSS** | 配置驱动的订阅源列表 | feedparser |
| **雪球** | 中国市场 KOL 观点 (20+ 大V) | Cookie 认证 |
| **GitHub Trending** | 关键词过滤的热门项目 | 页面解析 |
| **Yahoo Finance** | 黄金、商品、ticker 新闻 | yfinance |
| **Google News** | 查询驱动的新闻聚合 | RSS |
| **Reddit** | 每日热帖 (多个 subreddit) | RSS |
| **GitHub Releases** | 关注的 repo 发版监控 | GitHub API |
| **网页监控** | 博客 + 文档 commit 监控 | scrape + API |
| **ClawFeed** | KOL 内容导出 | CLI 集成 |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量 (可选)
cp .env.example .env
# ANTHROPIC_API_KEY — LLM 评分
# XUEQIU_COOKIE    — 雪球采集
# GITHUB_TOKEN     — GitHub API 限流

# 3. 启动 API（内置调度器自动采集）
python main.py
# → http://127.0.0.1:8001/docs

# 4. 启动前端
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

### 手动采集

```bash
python scripts/run_collectors.py                # 全部采集器
python scripts/run_collectors.py --source reddit # 指定数据源
python scripts/run_llm_tagger.py --limit 10     # LLM 评分
python scripts/run_llm_tagger.py --backfill     # 补评历史文章
```

## API

### 核心数据接口

| 端点 | 用途 |
|---|---|
| `GET /api/health` | 各数据源健康状态 (registry 驱动) |
| `GET /api/articles/latest` | 最新文章 `?limit=20&source=rss&min_relevance=4` |
| `GET /api/articles/search` | 关键词搜索 `?q=bitcoin&days=7` |
| `GET /api/articles/digest` | 按源分组 + 热门标签 |
| `GET /api/articles/signals` | 话题热度 + 叙事动量 `?hours=24` |
| `GET /api/articles/sources` | 各源历史统计 |

### 前端 Read Model

| 端点 | 用途 |
|---|---|
| `GET /api/ui/feed` | 优先级排序的信号流 |
| `GET /api/ui/items/{id}` | 文章详情 + 相关推荐 |
| `GET /api/ui/topics` | 话题列表 |
| `GET /api/ui/sources` | 活跃源列表 (registry 驱动) |
| `GET /api/ui/search` | 前端搜索 `?q=openai` |

## 标签体系

系统自动为每篇文章打上 **13 类标签**：

`ai` · `crypto` · `macro` · `geopolitics` · `china-market` · `us-market` · `trading` · `regulation` · `earnings` · `commodities` · `sector/tech` · `sector/finance` · `sector/energy`

**两层标签机制：**
1. **关键词标签** — 入库时基于正则自动匹配，零延迟
2. **LLM 标签** — Claude 评分相关度 (1-5) + 生成叙事标签，深度理解

## 技术栈

| 层 | 技术 |
|---|---|
| API | FastAPI · Uvicorn · Pydantic |
| 数据库 | SQLAlchemy 2.0 · SQLite |
| 采集 | feedparser · requests · yfinance |
| 调度 | APScheduler (后台自动运行) |
| AI | Anthropic Claude (相关度评分 + 叙事提取) |
| 前端 | React 18 · TypeScript · Vite · Tailwind · TanStack Query |

## 项目结构

```
├── main.py                 # FastAPI 入口 (port 8001)
├── config.py               # 源 seed 数据、采集配置
├── scheduler.py            # Registry 驱动的 APScheduler 调度器
├── sources/
│   ├── registry.py         # Source Registry CRUD
│   ├── adapters.py         # 源类型 → 采集器适配
│   ├── seed.py             # 从 config 播种 (insert-only)
│   └── resolver.py         # URL → source_type 分类器
├── api/
│   ├── routes.py           # 核心数据 API
│   └── ui_routes.py        # 前端 Read Model API
├── collectors/
│   ├── base.py             # BaseCollector 抽象类
│   ├── hackernews.py
│   ├── rss.py
│   ├── xueqiu.py
│   ├── yahoo_finance.py
│   ├── google_news.py
│   ├── reddit.py
│   ├── github_trending.py
│   ├── github_release.py
│   ├── webpage_monitor.py
│   └── clawfeed.py
├── db/
│   ├── models.py           # Article + SourceRegistry 模型
│   └── migrations.py       # 幂等 Schema 迁移
├── tagging/
│   ├── keywords.py         # 正则关键词标签 (13类)
│   └── llm.py              # Claude LLM 评分器
├── frontend/               # React 阅读工作台
├── scripts/                # 手动运行脚本
└── tests/                  # pytest 测试套件
```

## For AI Agents

本节面向需要将此项目作为工具或依赖集成的 AI Agent。

### 结构化元数据

```yaml
name: qualitative-data-pipeline
description: Qualitative signal workbench — collects, scores, and aggregates high-value market & tech content from 10+ sources into structured signal APIs
version: 0.1.0
api_base_url: http://localhost:8001
endpoints:
  - path: /api/articles/latest
    method: GET
    description: Recent articles sorted by time, filterable by source and relevance
    params:
      - name: limit
        type: integer
        required: false
        description: Max results (default 20)
      - name: source
        type: string
        required: false
        description: Filter by source (rss, hackernews, reddit, xueqiu, etc.)
      - name: min_relevance
        type: integer
        required: false
        description: Minimum LLM relevance score (1-5)
  - path: /api/articles/search
    method: GET
    description: Full-text keyword search across all articles
    params:
      - name: q
        type: string
        required: true
        description: Search query
      - name: days
        type: integer
        required: false
        description: Limit to recent N days
  - path: /api/articles/signals
    method: GET
    description: Topic heat, narrative momentum, relevance distribution
    params:
      - name: hours
        type: integer
        required: false
        description: Time window (default 24)
  - path: /api/articles/digest
    method: GET
    description: Articles grouped by source with top tags
  - path: /api/ui/feed
    method: GET
    description: Priority-scored feed with context rail data
  - path: /api/health
    method: GET
    description: Per-source health status (registry-driven)
install_command: pip install -r requirements.txt
start_command: python main.py
health_check: GET /api/health
dependencies:
  - fastapi
  - sqlalchemy
  - feedparser
  - requests
  - yfinance
  - anthropic
  - apscheduler
capabilities:
  - collect articles from 10+ sources (HN, RSS, Xueqiu, Reddit, GitHub, Yahoo Finance, Google News, etc.)
  - auto-tag articles with 13 keyword categories on ingest
  - score article relevance (1-5) and extract narrative tags via Claude LLM
  - track topic heat and narrative momentum over time
  - serve priority-ranked signal feed for trading decisions
input_format: No input required — collectors run on schedule via APScheduler
output_format: JSON API responses
```

### Agent 调用示例

```python
import httpx

async def get_trading_signals():
    base = "http://localhost:8001"

    # Step 1: 获取最近 24 小时的信号概览
    signals = await httpx.AsyncClient().get(f"{base}/api/articles/signals?hours=24")
    hot_topics = signals.json()

    # Step 2: 搜索特定关键词的高质量文章
    articles = await httpx.AsyncClient().get(
        f"{base}/api/articles/search",
        params={"q": "gold price", "days": 3}
    )
    results = articles.json()

    # Step 3: 获取优先级排序的信号流
    feed = await httpx.AsyncClient().get(f"{base}/api/ui/feed")
    top_items = feed.json()

    return {"signals": hot_topics, "search": results, "feed": top_items}
```

### MCP / Tool-Use 接口

```json
{
  "tool_name": "qualitative-data-pipeline",
  "description": "Query qualitative market signals from 10+ sources with relevance scoring",
  "parameters": {
    "action": {
      "type": "string",
      "enum": ["latest", "search", "signals", "digest", "feed"],
      "description": "要执行的查询类型"
    },
    "query": {
      "type": "string",
      "description": "搜索关键词 (action=search 时必填)"
    },
    "source": {
      "type": "string",
      "description": "数据源过滤 (hackernews, rss, xueqiu, reddit, etc.)"
    },
    "hours": {
      "type": "integer",
      "description": "时间窗口，单位小时 (action=signals 时使用)"
    },
    "min_relevance": {
      "type": "integer",
      "description": "最低相关度分数 1-5 (action=latest 时使用)"
    }
  }
}
```

## 相关项目

| 项目 | 说明 |
|---|---|
| [quant-data-pipeline](https://github.com/zinan92/quant-data-pipeline) | 定量数据管道 — A股、美股、加密、商品、债券、外汇 (port 8000) |

两个管道最终会汇入统一的交易决策系统：**定量提供数据，定性提供叙事**。

## License

MIT
