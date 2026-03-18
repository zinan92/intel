"""SQLAlchemy models for park-intel."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceRegistry(Base):
    """Internal source registry — the single source of truth for configured inputs."""

    __tablename__ = "source_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    owner_type: Mapped[str] = mapped_column(String, nullable=False, default="system")
    visibility: Mapped[str] = mapped_column(String, nullable=False, default="internal")
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_hours: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    __table_args__ = (
        Index("idx_source_registry_type", "source_type"),
        Index("idx_source_registry_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<SourceRegistry(key={self.source_key!r}, type={self.source_type!r})>"


class Article(Base):
    """Collected article from any source."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False)  # twitter, hackernews, substack
    source_id: Mapped[str | None] = mapped_column(String, unique=True)  # dedup key
    author: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    content: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String)
    tags: Mapped[str | None] = mapped_column(String)  # JSON array
    score: Mapped[int] = mapped_column(Integer, default=0)
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 LLM rating
    narrative_tags: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array from LLM
    tickers: Mapped[str | None] = mapped_column(String, nullable=True)  # JSON array
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    collected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_source", "source"),
        Index("idx_published", "published_at"),
        Index("idx_tags", "tags"),
    )

    def __repr__(self) -> str:
        return f"<Article(id={self.id}, source={self.source!r}, title={self.title!r})>"
