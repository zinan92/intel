# Technology Stack

**Analysis Date:** 2026-03-31

## Languages

**Primary:**
- Python 3.13.7 - Backend API, data collectors, scheduling, LLM integration
- TypeScript 5.6.3 - Frontend application with strict type checking
- JavaScript (ES2020) - Frontend runtime with modern module resolution

**Secondary:**
- SQL - SQLite database queries via SQLAlchemy ORM
- HTML/CSS - Via React JSX and Tailwind CSS

## Runtime

**Environment:**
- Python 3.13.7 (via `.venv` virtual environment)
- Node.js (for frontend build and dev tooling)

**Package Managers:**
- pip - Python dependencies managed via `requirements.txt`
- npm - JavaScript/TypeScript dependencies managed via `frontend/package.json`

## Frameworks

**Backend:**
- FastAPI 0.100.0+ - REST API framework, CORS middleware, async endpoints
- SQLAlchemy 2.0+ - ORM for SQLite database with declarative models
- APScheduler 3.10.0+ - Background job scheduler for periodic data collection
- Uvicorn 0.23.0+ - ASGI server (runs on port 8001)

**Frontend:**
- React 18.3.1 - UI component library
- React Router 6.28.0 - Client-side routing
- Vite 5.4.10 - Build tool and dev server (port 5174 with proxy to 8001)
- TypeScript compiler - Type checking during build

**Styling:**
- Tailwind CSS 3.4.15 - Utility-first CSS framework
- PostCSS 8.4.49 - CSS processing with autoprefixer

## Key Dependencies

**Critical Backend:**
- feedparser 6.0+ - RSS/Atom feed parsing for news sources
- requests 2.31+ - HTTP client for collector integrations (HN, GitHub, Xueqiu, RSS)
- httpx 0.27+ - Async HTTP client for quant bridge API calls
- yfinance 0.2.36+ - Yahoo Finance data fetching for market news
- anthropic 0.40.0+ - Claude API client for LLM tagging

**Infrastructure/Database:**
- python-dotenv 1.0+ - Environment variable loading from `.env`

**Frontend UI Components:**
- @radix-ui/react-dialog 1.1.2 - Modal dialog component
- @radix-ui/react-scroll-area 1.2.0 - Scrollable area component
- @radix-ui/react-separator 1.1.0 - Visual separator component
- @radix-ui/react-toast 1.2.2 - Toast notification system
- @tanstack/react-query 5.60.5 - Server state management
- @tanstack/react-query-devtools 5.60.5 - React Query development tools

**Frontend Visualization:**
- d3 7.9.0 - Data-driven visualization library for charts and diagrams
- @types/d3 7.4.3 - TypeScript types for D3

**Build & Development:**
- @vitejs/plugin-react 4.3.3 - React Fast Refresh plugin for Vite
- @types/react 18.3.12 - TypeScript types for React
- @types/react-dom 18.3.1 - TypeScript types for React DOM

## Configuration

**Environment:**
- Loaded via `python-dotenv` from `.env` file at project root
- Flask-style config module at `config.py` aggregates all settings

**Build:**
- Backend: FastAPI with uvicorn ASGI server
- Frontend: Vite with TypeScript compilation (`tsc && vite build`)
- Database: SQLite with WAL mode enabled for concurrent writes

**Dev Servers:**
- Backend: Runs on 127.0.0.1:8001
- Frontend: Runs on localhost:5174 with API proxy to http://localhost:8001

## Platform Requirements

**Development:**
- Python 3.13+
- Node.js (version not explicitly pinned in lockfile, but modern ESM support required)
- SQLite 3.x (included with Python)

**Production:**
- Python 3.13+ with FastAPI/Uvicorn
- Static frontend build artifacts deployable to CDN or Node.js
- SQLite database file persistence (or compatible SQL database if migrated)
- Network access to external APIs: Anthropic, Hacker News Algolia, Xueqiu, GitHub, Yahoo Finance, etc.

**Database:**
- SQLite stored at `data/park_intel.db`
- WAL journal mode enabled for performance
- Timeout: 30 seconds per connection

---

*Stack analysis: 2026-03-31*
