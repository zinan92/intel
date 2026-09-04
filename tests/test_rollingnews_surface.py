from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rollingnews_page_uses_the_read_only_same_origin_contract():
    page = (ROOT / "rollingnews" / "index.html").read_text(encoding="utf-8")

    assert "NEWS TRIAGE DESK — ROLLING NEWS" in page
    assert "<title>News Triage Desk — Rolling News</title>" in page
    assert "window.NEWS_API_BASE || ''" in page
    assert "/api/ui/realtime?window=24h&limit=120" in page
    assert "127.0.0.1:8001" not in page


def test_rollingnews_page_displays_received_time_as_primary_provenance():
    page = (ROOT / "rollingnews" / "index.html").read_text(encoding="utf-8")

    assert "'收 ' + timeLabel(item.collected_at)" in page
    assert "sourceTimeLabel(item)" in page
    assert "timeLabel(item.published_at || item.collected_at)" not in page
    assert "event.latest_collected_at" in page
    assert 'id="lastReceived"' in page
    assert 'id="lastTriaged"' in page
    assert "renderPipelineTimes(data.stats)" in page
    assert 'id="pendingHealth"' in page
    assert 'id="failedHealth"' in page
    assert "Park target registry exposure gate" in page
    assert "exposed + ' exposed" in page
    assert "filtered" in page
    assert "exposure_targets" in page
    assert "renderExposureTargets" in page
    assert "target.links_assets" in page


def test_rollingnews_launch_surface_is_scoped_to_static_directory():
    service = (ROOT / "scripts" / "rollingnews-static-service.sh").read_text(
        encoding="utf-8"
    )

    assert '"$PWD/scripts/serve_rollingnews.py"' in service
    assert "http.server" not in service


def test_rollingnews_cold_load_has_bounded_timeout_and_retry():
    page = (ROOT / "rollingnews" / "index.html").read_text(encoding="utf-8")

    assert "var FETCH_TIMEOUT_MS = 20000;" in page
    assert "var FETCH_RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 15000];" in page
    assert "function fetchRealtime" in page
    assert "AbortController" in page


def test_rollingnews_rate_uses_server_metric_and_distinguishes_unavailable():
    page = (ROOT / "rollingnews" / "index.html").read_text(encoding="utf-8")

    assert 'id="rate">rate unavailable<' in page
    assert "function renderIngestRate" in page
    assert "stats.ingest_rate" in page
    assert "headlines_per_minute" in page
    assert "window_minutes" in page
    assert "rate unavailable" in page
    assert "state.arrivalTimes" not in page
