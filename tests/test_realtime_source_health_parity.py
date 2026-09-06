from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Article, Base, CollectorRun, SourceRegistry


def test_quiet_sec_has_same_poll_status_but_explicit_stale_content(monkeypatch):
    import api.routes as core
    import api.ui_routes as ui
    import scheduler

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime.utcnow()
    session.add(SourceRegistry(source_key='sec_edgar:watchlist', source_type='sec_edgar',
                              display_name='SEC', config_json='{}', is_active=1,
                              lane='realtime', expected_freshness_hours=0.1))
    session.add_all([
        Article(source='sec_edgar', title='filing', collection_lane='realtime',
                collected_at=now-timedelta(days=3), is_backfill=False),
        Article(source='sec_edgar', title='archive', collection_lane='realtime',
                collected_at=now, is_backfill=True),
        CollectorRun(source_type='sec_edgar', status='ok', articles_fetched=2,
                     articles_saved=0, completed_at=now),
    ])
    session.commit()
    monkeypatch.setattr(core, 'get_session', lambda: session)
    monkeypatch.setattr(scheduler, 'get_last_results', lambda: {})
    monkeypatch.setenv('REALTIME_LANE_ENABLED', '1')
    source = core.health()['sources']['sec_edgar']
    ui_source = ui._build_source_health(session)[0]
    assert source['status'] == ui_source['status'] == 'ok'
    assert source['count'] == ui_source['count'] == 1
    assert source['freshness_status'] == 'stale'
    assert source['last_poll_at'] is not None
    session.close()
    engine.dispose()
