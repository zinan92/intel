"""Upgrade coverage for SEC registry rows created before CIK pinning."""

import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.migrations import run_migrations
from db.models import Base, SourceRegistry


def test_existing_sec_registry_row_receives_missing_cik_map_without_overwrites():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    original_config = {
        "tickers": ["NVDA", "SNDK"],
        "forms": ["8-K"],
        "operator_note": "keep-me",
    }
    with Session(engine) as session:
        session.add(SourceRegistry(
            source_key="sec_edgar:watchlist",
            source_type="sec_edgar",
            display_name="Operator SEC Source",
            config_json=json.dumps(original_config),
            is_active=0,
            lane="realtime",
            schedule_seconds=90,
        ))
        session.commit()

    run_migrations(engine)

    with Session(engine) as session:
        source = session.query(SourceRegistry).one()
        migrated = json.loads(source.config_json)
        assert migrated["cik_map"] == {"NVDA": 1045810, "SNDK": 2023554}
        assert migrated["tickers"] == ["NVDA", "SNDK"]
        assert migrated["forms"] == ["8-K"]
        assert migrated["operator_note"] == "keep-me"
        assert source.display_name == "Operator SEC Source"
        assert source.is_active == 0
        assert source.schedule_seconds == 90


def test_existing_nonempty_sec_cik_map_is_never_overwritten():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SourceRegistry(
            source_key="sec_edgar:watchlist",
            source_type="sec_edgar",
            display_name="SEC",
            config_json=json.dumps({
                "tickers": ["NVDA"],
                "forms": ["8-K"],
                "cik_map": {"NVDA": 9999999},
            }),
            is_active=1,
            lane="realtime",
            schedule_seconds=60,
        ))
        session.commit()

    run_migrations(engine)
    run_migrations(engine)

    with Session(engine) as session:
        source = session.query(SourceRegistry).one()
        assert json.loads(source.config_json)["cik_map"] == {"NVDA": 9999999}
