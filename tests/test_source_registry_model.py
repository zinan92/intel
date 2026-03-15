"""Tests for the SourceRegistry SQLAlchemy model and migration."""

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from db.models import Base, SourceRegistry


@pytest.fixture
def engine():
    """In-memory SQLite engine with all tables created."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    """Scoped session for test isolation."""
    factory = sessionmaker(bind=engine)
    sess = factory()
    yield sess
    sess.close()


class TestSourceRegistryModelExists:
    """SourceRegistry model exists and has the correct table name."""

    def test_model_class_exists(self):
        assert hasattr(SourceRegistry, "__tablename__")

    def test_table_name(self):
        assert SourceRegistry.__tablename__ == "source_registry"


class TestSourceRegistryTableCreation:
    """The source_registry table is created during metadata.create_all."""

    def test_table_created(self, engine):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "source_registry" in tables

    def test_required_columns_exist(self, engine):
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("source_registry")}
        expected = {
            "id",
            "source_key",
            "source_type",
            "display_name",
            "category",
            "config_json",
            "owner_type",
            "visibility",
            "is_active",
            "retired_at",
            "schedule_hours",
            "priority",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"


class TestSourceRegistryIndexes:
    """Indexes exist for performance-critical columns."""

    def test_indexes_created(self, engine):
        inspector = inspect(engine)
        indexes = inspector.get_indexes("source_registry")
        indexed_columns = set()
        for idx in indexes:
            for col in idx["column_names"]:
                indexed_columns.add(col)
        # source_key has a unique constraint which also acts as an index
        assert "source_type" in indexed_columns
        assert "is_active" in indexed_columns


class TestSourceRegistryCRUD:
    """Basic insert and query operations work."""

    def test_insert_and_read(self, session: Session):
        record = SourceRegistry(
            source_key="rss:openai-blog",
            source_type="rss",
            display_name="OpenAI Blog",
            category="llm",
            config_json=json.dumps({"url": "https://openai.com/blog/rss.xml"}),
            owner_type="system",
            visibility="internal",
            is_active=1,
            schedule_hours=6,
            priority=100,
        )
        session.add(record)
        session.commit()

        result = session.query(SourceRegistry).filter_by(source_key="rss:openai-blog").first()
        assert result is not None
        assert result.source_type == "rss"
        assert result.display_name == "OpenAI Blog"
        assert result.category == "llm"
        assert result.owner_type == "system"
        assert result.visibility == "internal"
        assert result.is_active == 1
        assert result.schedule_hours == 6
        assert result.priority == 100
        assert json.loads(result.config_json) == {"url": "https://openai.com/blog/rss.xml"}

    def test_source_key_unique(self, session: Session):
        record1 = SourceRegistry(
            source_key="rss:test",
            source_type="rss",
            display_name="Test Feed",
            config_json="{}",
        )
        record2 = SourceRegistry(
            source_key="rss:test",
            source_type="rss",
            display_name="Duplicate Feed",
            config_json="{}",
        )
        session.add(record1)
        session.commit()
        session.add(record2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()

    def test_defaults(self, session: Session):
        record = SourceRegistry(
            source_key="reddit:test",
            source_type="reddit",
            display_name="Test Subreddit",
            config_json="{}",
        )
        session.add(record)
        session.commit()

        result = session.query(SourceRegistry).filter_by(source_key="reddit:test").first()
        assert result is not None
        assert result.owner_type == "system"
        assert result.visibility == "internal"
        assert result.is_active == 1
        assert result.priority == 100
        assert result.retired_at is None
        assert result.category is None
        assert result.schedule_hours is None


class TestSourceRegistryMigration:
    """Migration adds the source_registry table to existing databases."""

    def test_migration_creates_table(self):
        from db.migrations import run_migrations

        engine = create_engine("sqlite:///:memory:")
        # Create only the articles table first (simulating existing DB)
        from db.models import Article
        Article.__table__.create(engine)

        # Run migrations — should create source_registry
        run_migrations(engine)

        inspector = inspect(engine)
        assert "source_registry" in inspector.get_table_names()
