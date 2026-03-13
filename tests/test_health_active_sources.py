"""Tests for active-source-driven /api/health semantics."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


FAKE_ACTIVE = [
    {"source": "hackernews", "interval_hours": 4, "category": "frontier-tech"},
    {"source": "brand_new_xyz", "interval_hours": 6, "category": "mixed"},
]
RETIRED = ["twitter", "youtube", "substack"]


@pytest.fixture
def client():
    with patch("main.CollectorScheduler.start"), patch("main.CollectorScheduler.shutdown"):
        from main import app
        with TestClient(app) as test_client:
            yield test_client


def test_health_excludes_retired_sources(client):
    with patch("api.routes.config.ACTIVE_SOURCES", FAKE_ACTIVE):
        resp = client.get("/api/health")
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    for r in RETIRED:
        assert r not in sources, f"Retired source '{r}' must not appear in /api/health"


def test_health_includes_all_active_sources(client):
    with patch("api.routes.config.ACTIVE_SOURCES", FAKE_ACTIVE):
        resp = client.get("/api/health")
    sources = resp.json()["sources"]
    for entry in FAKE_ACTIVE:
        assert entry["source"] in sources


def test_health_no_data_status_for_unseen_source(client):
    with patch("api.routes.config.ACTIVE_SOURCES",
               [{"source": "brand_new_xyz", "interval_hours": 6, "category": "mixed"}]):
        resp = client.get("/api/health")
    sources = resp.json()["sources"]
    assert sources["brand_new_xyz"]["status"] == "no_data"
