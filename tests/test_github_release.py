"""Tests for GitHubReleaseCollector — auth/no-auth behavior and mapping."""
from unittest.mock import MagicMock, patch

import pytest
from collectors.github_release import GitHubReleaseCollector

FAKE_REPOS = [
    {"repo": "owner/repo-a", "category": "ai-agent"},
    {"repo": "owner/repo-b", "category": "ai-agent"},
]

SAMPLE_RELEASE = {
    "id": 12345,
    "tag_name": "v1.2.3",
    "html_url": "https://github.com/owner/repo-a/releases/tag/v1.2.3",
    "body": "This release includes new features and bug fixes.",
    "author": {"login": "octocat"},
    "published_at": "2024-01-15T10:00:00Z",
}


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


def test_collect_returns_list():
    with patch("collectors.github_release.requests.get", return_value=_mock_response([])), \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", FAKE_REPOS), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        result = GitHubReleaseCollector().collect()
    assert isinstance(result, list)


def test_mapping_fields():
    resp = _mock_response([SAMPLE_RELEASE])
    with patch("collectors.github_release.requests.get", return_value=resp), \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", [FAKE_REPOS[0]]), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        result = GitHubReleaseCollector().collect()
    assert len(result) == 1
    a = result[0]
    assert a["source"] == "github_release"
    assert a["title"] == "repo-a v1.2.3"
    assert a["url"] == "https://github.com/owner/repo-a/releases/tag/v1.2.3"
    assert a["author"] == "octocat"
    assert a["content"] == "This release includes new features and bug fixes."


def test_source_id_uses_release_id():
    resp = _mock_response([SAMPLE_RELEASE])
    with patch("collectors.github_release.requests.get", return_value=resp), \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", [FAKE_REPOS[0]]), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        result = GitHubReleaseCollector().collect()
    assert result[0]["source_id"] == "github_release_12345"


def test_source_id_fallback_to_repo_tag():
    release_no_id = {k: v for k, v in SAMPLE_RELEASE.items() if k != "id"}
    resp = _mock_response([release_no_id])
    with patch("collectors.github_release.requests.get", return_value=resp), \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", [FAKE_REPOS[0]]), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        r1 = GitHubReleaseCollector().collect()
    with patch("collectors.github_release.requests.get", return_value=resp), \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", [FAKE_REPOS[0]]), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        r2 = GitHubReleaseCollector().collect()
    assert r1[0]["source_id"] == r2[0]["source_id"]
    assert r1[0]["source_id"].startswith("github_release_")


def test_auth_header_sent_when_token_set():
    with patch("collectors.github_release.requests.get") as mock_get, \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", [FAKE_REPOS[0]]), \
         patch("collectors.github_release.config.GITHUB_TOKEN", "mytoken"):
        mock_get.return_value = _mock_response([])
        GitHubReleaseCollector().collect()
    call_headers = mock_get.call_args.kwargs.get("headers") or mock_get.call_args[1].get("headers", {})
    assert call_headers.get("Authorization") == "Bearer mytoken"


def test_no_auth_header_when_no_token():
    with patch("collectors.github_release.requests.get") as mock_get, \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", [FAKE_REPOS[0]]), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        mock_get.return_value = _mock_response([])
        GitHubReleaseCollector().collect()
    call_headers = mock_get.call_args.kwargs.get("headers") or mock_get.call_args[1].get("headers", {})
    assert "Authorization" not in call_headers


def test_404_repo_continues_gracefully():
    resp_404 = _mock_response([], status_code=404)
    resp_404.raise_for_status = MagicMock()  # 404 is handled before raise_for_status
    good_resp = _mock_response([SAMPLE_RELEASE])
    responses = [resp_404, good_resp]
    call_count = [0]
    def get_side_effect(url, **kw):
        r = responses[call_count[0]]
        call_count[0] += 1
        return r
    with patch("collectors.github_release.requests.get", side_effect=get_side_effect), \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", FAKE_REPOS), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        result = GitHubReleaseCollector().collect()
    assert len(result) == 1


def test_category_in_tags():
    resp = _mock_response([SAMPLE_RELEASE])
    with patch("collectors.github_release.requests.get", return_value=resp), \
         patch("collectors.github_release.config.GITHUB_RELEASE_REPOS", [FAKE_REPOS[0]]), \
         patch("collectors.github_release.config.GITHUB_TOKEN", ""):
        result = GitHubReleaseCollector().collect()
    assert "ai-agent" in result[0]["tags"]
