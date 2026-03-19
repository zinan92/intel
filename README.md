<div align="center">

# qualitative-data-pipeline

**交易信号情报站 — 从 10+ 数据源自动发现跨源验证的市场信号**

采集 → 评分 → 聚合 → 可视化，把信息噪音变成可操作的交易 insight

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](#)
[![React 18](https://img.shields.io/badge/React_18-61DAFB?style=flat-square&logo=react&logoColor=black)](#)
[![Claude AI](https://img.shields.io/badge/Claude_AI-000?style=flat-square&logo=anthropic&logoColor=white)](#)
[![D3.js](https://img.shields.io/badge/D3.js-F9A03C?style=flat-square&logo=d3.js&logoColor=white)](#)
[![Tests](https://img.shields.io/badge/tests-290%2B_passing-brightgreen?style=flat-square)](#)

</div>

---

## 痛点

交易员每天面对海量信息：推特、雪球、HN、新闻、GitHub——分散在十几个平台。真正重要的信号被淹没在噪音里，等你看到时已经过时了。

## 解决方案

自动从 10+ 源采集内容，LLM 评分筛选，**跨源聚合成事件**（同一件事在 HN、Reddit、Google News 同时出现 = 信号可信度高），生成 AI 摘要，关联 ticker 价格影响。打开即看到今天最重要的 5 件事。

## 核心能力

| 能力 | 说明 | 状态 |
|------|------|------|
| 10 源自动采集 | HN · RSS · 雪球 · Reddit · Yahoo Finance · Google News 等 | ✅ |
| 13 类关键词标签 | 入库即标注：ai, crypto, macro, trading, earnings... | ✅ |
| LLM 相关度评分 | Claude 打分 1-5 + 生成叙事标签 | ✅ |
| **跨源事件聚合** | 同 narrative_tag 48h 内多源命中 → 事件，信号分 = 源数 × 平均相关度 | ✅ |
| **AI 事件摘要** | Claude CLI 为每个跨源事件生成 2-3 句交易员视角摘要 | ✅ |
| **Signal Velocity** | 事件信号趋势箭头（↑变强 / ↓变弱 / NEW 新出现） | ✅ |
| **Ticker 提取** | $NVDA cashtag + 中英文公司名映射（36+ 公司），自动关联股票 | ✅ |
| **Quant Bridge** | 异步拉取 quant-data-pipeline 价格数据，展示事件后 1/3/5 日涨跌幅 | ✅ |
| **用户个性化** | 每人 13 个 topic 权重（0=隐藏, 3=最大提权），个性化 Feed 排序 | ✅ |
| **Morning Brief** | 首页 hero 事件 + 2×2 网格，打开即知道今天最重要的事 | ✅ |
| **Event Constellation** | D3.js 力导向图，事件按 Crypto/AI/Macro 聚类，ticker 连线可视化 | 🔬 原型 |
| 事件历史存档 | 30 天关闭事件可搜索回顾 | ✅ |

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    数据源 (10 Collectors)                     │
│  HN · RSS · 雪球 · GitHub · Yahoo · Google · Reddit · KOL   │
└────────────────────────┬────────────────────────────────────┘
                         │ 采集 + 去重
                         ▼
              ┌──────────────────┐
              │   关键词标签 (13类)  │ ← 零延迟，入库即标注
              │   Ticker 提取      │ ← $NVDA + 公司名映射
              └────────┬─────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   LLM 评分器     事件聚合器      调度器
   (Claude)     (48h 窗口)    (APScheduler)
   相关度 1-5    跨源聚类          │
   叙事标签     信号分计算         │
   事件摘要     Velocity          │
          └────────────┼────────────┘
                       ▼
              ┌──────────────────┐
              │   FastAPI APIs    │
              │  /api/* + /ui/*   │
              └────────┬─────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    React 前端    Quant Bridge   用户系统
   Morning Brief  价格影响数据   个性化权重
   Event Detail   1D/3D/5D      Topic 过滤
   Constellation  涨跌幅
   Event History
```

## 数据源

| 源 | 说明 | 采集方式 |
|---|---|---|
| **Hacker News** | 科技前沿，score ≥ 20 | Algolia API |
| **RSS** | 50+ 订阅源（博客、newsletter） | feedparser |
| **雪球** | 中国市场 KOL 观点 (20+ 大V) | Cookie 认证 |
| **GitHub Trending** | 关键词过滤的热门项目 | 页面解析 |
| **Yahoo Finance** | 黄金、商品、ticker 新闻 | yfinance |
| **Google News** | 查询驱动的新闻聚合 | RSS |
| **Reddit** | 13 个 subreddit 热帖 | RSS |
| **GitHub Releases** | 关注的 repo 发版监控 | GitHub API |
| **网页监控** | 博客 + 文档 commit 监控 | scrape + API |
| **ClawFeed** | 22 个 KOL 内容导出 | CLI 集成 |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量 (全部可选)
cp .env.example .env
# ANTHROPIC_API_KEY — LLM 评分 + 事件摘要
# XUEQIU_COOKIE    — 雪球采集
# GITHUB_TOKEN     — GitHub API 限流

# 3. 启动 API（内置调度器自动采集）
python main.py
# → http://127.0.0.1:8001

# 4. 启动前端
cd frontend && npm install && npm run dev
# → http://localhost:5174
```

### 手动操作

```bash
python scripts/run_collectors.py                # 全部采集
python scripts/run_collectors.py --source reddit # 指定源
python scripts/run_llm_tagger.py --limit 10     # LLM 评分
python scripts/run_llm_tagger.py --backfill     # 补评历史
python scripts/backfill_tickers.py              # 补充 Ticker 提取
```

## API

### 核心数据

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
| `GET /api/ui/feed` | 优先级排序的信号流 `?user=wendy&window=24h` |
| `GET /api/ui/items/{id}` | 文章详情 + 相关推荐 |
| `GET /api/ui/topics` | 话题列表 |
| `GET /api/ui/sources` | 活跃源列表 (registry 驱动) |
| `GET /api/ui/search` | 前端搜索 `?q=openai` |

### 事件系统

| 端点 | 用途 |
|---|---|
| `GET /api/events/active` | 活跃事件列表（按信号分排序） |
| `GET /api/events/{id}` | 事件详情 + 文章时间线 + 价格影响 |
| `GET /api/events/history` | 30 天关闭事件存档 `?tag=btc&days=30` |

### 用户系统

| 端点 | 用途 |
|---|---|
| `POST /api/users` | 创建用户 |
| `GET /api/users/{username}` | 获取用户 + topic 权重 |
| `PUT /api/users/{username}/weights` | 更新 topic 权重 (0.0-3.0) |

## 信号系统

### 三层标签

1. **关键词标签** (13 类) — 入库即匹配，零延迟
   `ai` · `crypto` · `macro` · `geopolitics` · `china-market` · `us-market` · `trading` · `regulation` · `earnings` · `commodities` · `sector/tech` · `sector/finance` · `sector/energy`

2. **LLM 叙事标签** — Claude 深度理解，生成事件描述符如 `nvidia-earnings-beat`、`fed-rate-pause`

3. **Ticker 提取** — `$NVDA` cashtag + 中英文公司名（NVIDIA/英伟达 → NVDA），36+ 映射

### 事件聚合

同一个叙事标签在 48h 内被 2+ 个不同数据源报道 → 自动聚合为 **事件**

- **信号分** = 命中源数量 × 平均相关度
- **时效衰减** = 24h 半衰期，新事件自动优先
- **AI 摘要** = Claude 为每个跨源事件生成 2-3 句交易员视角摘要
- **Signal Velocity** = 对比上次聚合的信号分，显示 ↑/↓/→/NEW

## 技术栈

| 层 | 技术 |
|---|---|
| API | FastAPI · Uvicorn · Pydantic |
| 数据库 | SQLAlchemy 2.0 · SQLite (WAL mode) |
| 采集 | feedparser · requests · yfinance · httpx |
| 调度 | APScheduler (后台自动运行) |
| AI | Anthropic Claude (评分 + 叙事 + 事件摘要) |
| 前端 | React 18 · TypeScript · Vite · Tailwind · TanStack Query |
| 可视化 | D3.js (Event Constellation 力导向图) |
| 测试 | pytest (290+ tests) |

## 项目结构

```
├── main.py                 # FastAPI 入口 (port 8001)
├── config.py               # 源 seed 数据、采集配置、Ticker 映射
├── scheduler.py            # Registry 驱动的 APScheduler + 事件聚合
├── sources/                # 数据源管理
│   ├── registry.py         # Source Registry CRUD
│   ├── adapters.py         # 源类型 → 采集器适配
│   └── seed.py             # 从 config 播种 (insert-only)
├── api/
│   ├── routes.py           # 核心数据 API
│   ├── ui_routes.py        # 前端 Read Model + Morning Brief
│   ├── event_routes.py     # 事件 API (active, detail, history)
│   └── user_routes.py      # 用户 API (CRUD, weights)
├── collectors/             # 10 个数据源采集器
│   ├── base.py             # BaseCollector (去重 + 标签 + Ticker)
│   ├── hackernews.py · rss.py · xueqiu.py · reddit.py
│   ├── yahoo_finance.py · google_news.py · github_trending.py
│   ├── github_release.py · webpage_monitor.py · social_kol.py
├── events/                 # 事件聚合系统
│   ├── models.py           # Event + EventArticle 模型
│   ├── aggregator.py       # 48h 窗口聚类 + velocity
│   └── narrator.py         # Claude CLI 事件摘要生成
├── users/                  # 用户个性化
│   ├── models.py           # UserProfile (topic_weights)
│   └── service.py          # CRUD + 权重验证
├── bridge/
│   └── quant.py            # Async 价格数据 (httpx → quant-data-pipeline)
├── tagging/
│   ├── keywords.py         # 正则关键词标签 (13类)
│   ├── tickers.py          # Ticker 提取 (cashtag + 别名)
│   └── llm.py              # Claude LLM 评分器
├── db/
│   ├── models.py           # Article + SourceRegistry + Event + UserProfile
│   ├── database.py         # Engine, Session, init_db
│   └── migrations.py       # 幂等 Schema 迁移
├── frontend/               # React 暗色终端风格 UI
│   ├── src/components/     # MorningBrief, EventCard, FeedCard, ContextRail
│   └── src/pages/          # Feed, Event, EventHistory, Settings, Search
├── scripts/                # 手动运行脚本
├── tests/                  # 290+ pytest 测试
└── plans/                  # 设计文档 + 实施计划
```

## 配置

| 变量 | 说明 | 必填 | 默认值 |
|------|------|------|--------|
| `ANTHROPIC_API_KEY` | Claude API (LLM 评分) | 否 | CLI fallback |
| `XUEQIU_COOKIE` | 雪球登录 cookie | 否 | 跳过雪球采集 |
| `GITHUB_TOKEN` | GitHub API token | 否 | 受限速率 |
| `QUANT_API_BASE_URL` | quant-data-pipeline 地址 | 否 | `http://localhost:8000` |

## For AI Agents

本节面向需要将此项目作为工具或依赖集成的 AI Agent。

### 结构化元数据

```yaml
name: qualitative-data-pipeline
description: Trading signal intelligence — collects from 10+ sources, LLM-scores relevance, clusters cross-source events with AI narratives, extracts tickers, and bridges to quantitative price data
version: 2.0.0
api_base_url: http://localhost:8001
endpoints:
  - path: /api/articles/latest
    method: GET
    description: Recent articles filterable by source and relevance
    params:
      - name: limit
        type: integer
        required: false
      - name: source
        type: string
        required: false
      - name: min_relevance
        type: integer
        required: false
  - path: /api/articles/signals
    method: GET
    description: Topic heat, narrative momentum, relevance distribution
    params:
      - name: hours
        type: integer
        required: false
  - path: /api/events/active
    method: GET
    description: Active cross-source events ranked by freshness-weighted signal score
  - path: /api/events/{id}
    method: GET
    description: Event detail with article timeline, AI narrative, and price impacts
  - path: /api/ui/feed
    method: GET
    description: Priority-scored feed with Morning Brief and personalization
    params:
      - name: user
        type: string
        required: false
      - name: min_relevance
        type: integer
        required: false
      - name: window
        type: string
        required: false
  - path: /api/events/history
    method: GET
    description: Closed events from last N days with tag filtering
    params:
      - name: days
        type: integer
        required: false
      - name: tag
        type: string
        required: false
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
  - httpx
capabilities:
  - collect articles from 10+ sources on schedule
  - auto-tag with 13 keyword categories and extract stock tickers
  - score relevance (1-5) and generate narrative tags via Claude
  - cluster cross-source events with signal scoring and AI summaries
  - track signal velocity (strengthening/weakening trends)
  - bridge to quantitative data for price impact analysis
  - personalize feed ranking per user with topic weights
input_format: No input required — collectors run on schedule
output_format: JSON API responses
```

### Agent 调用示例

```python
import httpx

async def get_trading_intelligence():
    base = "http://localhost:8001"
    async with httpx.AsyncClient() as client:
        # 获取当前最重要的跨源事件
        events = await client.get(f"{base}/api/events/active")
        top_events = events.json()["events"]

        # 查看最高信号分事件的详情（含 AI 摘要 + 价格影响）
        if top_events:
            detail = await client.get(f"{base}/api/events/{top_events[0]['id']}")
            event = detail.json()
            # event["event"]["narrative_summary"] → AI 生成的交易员摘要
            # event["price_impacts"] → [{ticker, price_at_event, change_1d, ...}]

        # 获取个性化信号流
        feed = await client.get(f"{base}/api/ui/feed", params={"user": "wendy"})
        # feed["context"]["top_events"] → Morning Brief 数据

        return {"events": top_events, "detail": event, "feed": feed.json()}
```

### MCP / Tool-Use 接口

```json
{
  "tool_name": "qualitative-data-pipeline",
  "description": "Query cross-source trading signals with AI narratives and price impacts",
  "parameters": {
    "action": {
      "type": "string",
      "enum": ["events", "event_detail", "feed", "search", "signals", "history"],
      "description": "查询类型"
    },
    "event_id": {
      "type": "integer",
      "description": "事件 ID (action=event_detail 时必填)"
    },
    "query": {
      "type": "string",
      "description": "搜索关键词 (action=search 时必填)"
    },
    "user": {
      "type": "string",
      "description": "用户名，启用个性化排序 (action=feed 时可选)"
    },
    "hours": {
      "type": "integer",
      "description": "时间窗口 (action=signals 时使用)"
    }
  }
}
```

## 相关项目

| 项目 | 说明 |
|---|---|
| [quant-data-pipeline](https://github.com/zinan92/quant-data-pipeline) | 定量数据管道 — A股、美股、加密、商品、债券、外汇 (port 8000) |

两个管道构成完整的交易决策系统：**定量提供价格数据，定性提供叙事信号**。Quant Bridge 已打通两端。

## License

MIT
