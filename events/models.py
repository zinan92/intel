"""SQLAlchemy models for event aggregation."""
from datetime import datetime

from sqlalchemy import (
    DateTime, Float, Integer, String, Text,
    Index, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class Event(Base):
    """Aggregated event from cross-source narrative tag clustering."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    narrative_tag: Mapped[str] = mapped_column(String, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    article_count: Mapped[int] = mapped_column(Integer, default=0)
    signal_score: Mapped[float] = mapped_column(Float, default=0.0)
    avg_relevance: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="active")
    narrative_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_signal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index("idx_events_tag", "narrative_tag"),
        Index("idx_events_status", "status"),
        Index("idx_events_score", "signal_score"),
    )


class EventArticle(Base):
    """Many-to-many link between events and articles."""

    __tablename__ = "event_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "article_id", name="uq_event_article"),
    )
