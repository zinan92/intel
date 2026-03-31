"""park-intel — FastAPI application."""

import logging
import logging.handlers
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.event_routes import event_router
from api.health_routes import health_router
from api.routes import router
from api.ui_routes import ui_router
from api.user_routes import user_router
from config import API_HOST, API_PORT, BASE_DIR, CORS_ORIGINS
from db.database import init_db
from scheduler import CollectorScheduler

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set up root logger with rotating file handler."""
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        log_dir / "park-intel.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize DB and start collector scheduler on startup."""
    _configure_logging()
    init_db()
    collector_scheduler = CollectorScheduler()
    collector_scheduler.start()
    logger.info("park-intel started with built-in collector scheduler")
    yield
    collector_scheduler.shutdown()


app = FastAPI(
    title="park-intel",
    description="Qualitative data pipeline — Twitter, Hacker News, Substack",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(ui_router)
app.include_router(event_router)
app.include_router(user_router)
app.include_router(health_router)

# Serve frontend static files (built with `cd frontend && npm run build`)
_frontend_dist = BASE_DIR / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="static")

    @app.get("/{path:path}")
    async def _serve_frontend(path: str) -> FileResponse:
        """Serve frontend SPA — all non-API routes fall through to index.html."""
        file_path = _frontend_dist / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=os.getenv("PARK_INTEL_DEV", "") == "1",
    )
