"""Reproduce writer contention at real collector/model boundaries."""
import sqlite3
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base
from events.models import Event, EventArticle


def test_other_writer_can_commit_during_every_narrative_call(tmp_path, monkeypatch):
    from events import narrator

    path = tmp_path / 'concurrent.db'
    engine = create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.exec_driver_sql('PRAGMA journal_mode=WAL')
    session = Session(engine)
    now = datetime.utcnow()
    for i in range(2):
        event = Event(narrative_tag=f'event-{i}', source_count=2, status='active',
                      window_start=now-timedelta(hours=1), window_end=now+timedelta(hours=1))
        article = Article(source='rss', title='fixture', collected_at=now)
        session.add_all([event, article])
        session.flush()
        session.add(EventArticle(event_id=event.id, article_id=article.id))
    session.commit()
    calls = []

    def model_call(prompt):
        with sqlite3.connect(path, timeout=0.1) as writer:
            writer.execute('UPDATE articles SET score=score+1 WHERE id=1')
        calls.append(prompt)
        return 'summary', 'codex-cli', None

    monkeypatch.setattr(narrator, '_call_llm', model_call)
    monkeypatch.setattr(narrator.time, 'sleep', lambda _: None)
    try:
        result = narrator.generate_narratives(session)
        assert result.generated == 2
        assert len(calls) == 2
    finally:
        session.close()
        engine.dispose()


def test_repeated_collector_initialization_does_not_request_writer_lock(tmp_path, monkeypatch):
    import db.database as db
    from collectors.base import BaseCollector

    path = tmp_path / 'init.db'
    engine = create_engine(f'sqlite:///{path}', connect_args={'timeout': 0.1})
    monkeypatch.setattr(db, '_engine', engine)
    monkeypatch.setattr(db, '_SessionFactory', None)
    db.init_db()

    class Saver(BaseCollector):
        def collect(self):
            return []

    writer = sqlite3.connect(path, timeout=0.1)
    writer.execute('BEGIN IMMEDIATE')
    try:
        Saver()
    finally:
        writer.rollback()
        writer.close()
        engine.dispose()
