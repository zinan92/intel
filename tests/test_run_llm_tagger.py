"""End-to-end tagger run status and article provenance tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Article, Base, CollectorRun
from tagging.llm import TagBatchResult, TaggingError


def _database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _article(session) -> Article:
    article = Article(
        source="rss",
        source_id="tagger-test",
        title="Fed decision",
        content="Rates changed",
        collected_at=datetime(2026, 9, 3, 1, 0),
        collection_lane="hourly",
    )
    session.add(article)
    session.commit()
    return article


def test_run_tagger_persists_scores_provider_and_success_status():
    from scripts import run_llm_tagger as mod

    Session = _database()
    seed_session = Session()
    article = _article(seed_session)
    article_id = article.id
    seed_session.close()

    tagger = Mock()
    tagger.batches_processed = 1
    tagger.tag_batch.return_value = TagBatchResult(
        ({"id": article_id, "relevance_score": 5, "narrative_tags": ["fed-rate-shock"]},),
        "codex-cli",
        "DeepSeekError",
    )

    with patch.object(mod, "init_db", return_value=None), \
         patch.object(mod, "get_session", side_effect=Session):
        result = mod.run_tagger(limit=1, tagger=tagger)

    session = Session()
    refreshed = session.get(Article, article_id)
    run = session.query(CollectorRun).filter_by(source_type="llm_tagger").one()
    assert result.status == "ok"
    assert result.attempted == 1
    assert result.scored == 1
    assert result.provider == "codex-cli"
    assert refreshed.relevance_score == 5
    assert refreshed.relevance_provider == "codex-cli"
    assert refreshed.relevance_scored_at is not None
    assert run.status == "ok"
    assert run.provider == "codex-cli"
    assert run.fallback_reason == "DeepSeekError"
    session.close()


def test_run_tagger_records_failure_and_raises_when_scoring_fails():
    from scripts import run_llm_tagger as mod

    Session = _database()
    seed_session = Session()
    _article(seed_session)
    seed_session.close()

    tagger = Mock()
    tagger.batches_processed = 0
    tagger.tag_batch.side_effect = TaggingError("both providers failed")

    with patch.object(mod, "init_db", return_value=None), \
         patch.object(mod, "get_session", side_effect=Session), \
         pytest.raises(mod.TaggerRunError, match="both providers failed"):
        mod.run_tagger(limit=1, tagger=tagger)

    session = Session()
    run = session.query(CollectorRun).filter_by(source_type="llm_tagger").one()
    assert run.status == "error"
    assert run.articles_fetched == 1
    assert run.articles_saved == 0
    assert run.articles_failed == 1
    assert run.error_message == "both providers failed"
    session.close()


def test_run_tagger_limits_recovery_to_explicit_window():
    from scripts import run_llm_tagger as mod

    Session = _database()
    session = Session()
    window_end = datetime(2026, 8, 30, 0, 0)
    inside = Article(
        source="rss",
        source_id="inside-window",
        title="Inside",
        collected_at=window_end - timedelta(hours=1),
        collection_lane="hourly",
    )
    outside = Article(
        source="rss",
        source_id="outside-window",
        title="Outside",
        collected_at=window_end - timedelta(days=2),
        collection_lane="hourly",
    )
    session.add_all([inside, outside])
    session.commit()
    inside_id = inside.id
    outside_id = outside.id
    session.close()

    tagger = Mock()
    tagger.batches_processed = 1
    tagger.tag_batch.side_effect = lambda rows: TagBatchResult(
        tuple({"id": row["id"], "relevance_score": 4, "narrative_tags": ["bounded"]} for row in rows),
        "codex-cli",
        "DeepSeekError",
    )

    with patch.object(mod, "init_db", return_value=None), \
         patch.object(mod, "get_session", side_effect=Session):
        result = mod.run_tagger(
            limit=300,
            window_start=window_end - timedelta(hours=24),
            window_end=window_end,
            tagger=tagger,
        )

    session = Session()
    assert result.scored == 1
    assert session.get(Article, inside_id).relevance_score == 4
    assert session.get(Article, outside_id).relevance_score is None
    session.close()
