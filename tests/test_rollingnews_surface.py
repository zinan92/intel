from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rollingnews_page_uses_the_read_only_same_origin_contract():
    page = (ROOT / "rollingnews" / "index.html").read_text(encoding="utf-8")

    assert "NEWS TRIAGE DESK — ROLLING NEWS" in page
    assert "<title>News Triage Desk — Rolling News</title>" in page
    assert "window.NEWS_API_BASE || ''" in page
    assert "/api/ui/realtime?window=24h&limit=120" in page
    assert "127.0.0.1:8001" not in page


def test_rollingnews_launch_surface_is_scoped_to_static_directory():
    service = (ROOT / "scripts" / "rollingnews-static-service.sh").read_text(
        encoding="utf-8"
    )

    assert "--bind 127.0.0.1" in service
    assert "--directory \"$PWD/rollingnews\"" in service
    assert "8787" in service
