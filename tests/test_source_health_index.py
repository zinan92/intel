"""#129: the source-health aggregate reads a covering index, not every article row.

`_build_source_health` (behind /api/ui/realtime) and /api/health count every non-backfill article per source
and take the latest collected_at. With only `idx_source (source)`, SQLite read each matching row from the table:
2.7 s on the production database, twice per /api/health.
"""
from __future__ import annotations

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session

from db.migrations import run_migrations
from db.models import Article, Base


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'health.db'}")
    Base.metadata.create_all(engine)
    return engine


def _aggregate_sql(engine) -> tuple[str, list]:
    """The statement both health paths run, compiled by SQLAlchemy as they do."""
    with Session(engine) as session:
        query = (
            session.query(Article.source, func.count(Article.id), func.max(Article.collected_at))
            .filter(Article.source.in_(["cls_telegraph", "rss"]), Article.is_backfill.is_(False))
            .group_by(Article.source)
        )
        compiled = query.statement.compile(engine, compile_kwargs={"render_postcompile": True})
        return str(compiled), [compiled.params[name] for name in compiled.positiontup]


def test_migrations_create_the_source_health_index(tmp_path) -> None:
    engine = _engine(tmp_path)
    run_migrations(engine)
    run_migrations(engine)  # idempotent
    with engine.connect() as conn:
        columns = [row[2] for row in conn.execute(text("PRAGMA index_info(idx_articles_source_backfill_collected)"))]
    assert columns == ["source", "is_backfill", "collected_at"]


def test_the_source_health_aggregate_uses_only_the_index(tmp_path) -> None:
    engine = _engine(tmp_path)
    run_migrations(engine)
    engine.dispose()  # plan on a new connection, as a restarted service would
    sql, params = _aggregate_sql(engine)
    with engine.connect() as conn:
        plan = " | ".join(row[3] for row in conn.exec_driver_sql("EXPLAIN QUERY PLAN " + sql, tuple(params)))
    assert "COVERING INDEX idx_articles_source_backfill_collected" in plan, plan


def test_after_startup_every_pooled_connection_uses_the_index(tmp_path, monkeypatch) -> None:
    """After the service's real startup path (init_db), a request's connection plans with the new index.

    A connection that ran only create_all + run_migrations kept planning with idx_source; init_db's later
    session work (seeding, source canonicalisation) does not, and this guards that path.
    """
    import db.database as db

    path = tmp_path / "existing.db"
    earlier = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(earlier)  # the database exists from an earlier run, without the new index
    earlier.dispose()

    engine = create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(db, "_engine", engine)
    monkeypatch.setattr(db, "_SessionFactory", None)
    db.init_db()  # what the service does on start
    try:
        sql, params = _aggregate_sql(engine)
        raw = engine.raw_connection()  # the pool hands out the next connection, as a request would get it
        try:
            plan = " | ".join(row[3] for row in raw.driver_connection.execute("EXPLAIN QUERY PLAN " + sql, params))
        finally:
            raw.close()
        assert "COVERING INDEX idx_articles_source_backfill_collected" in plan, plan
    finally:
        engine.dispose()
