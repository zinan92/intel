from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from llm.deepseek import DeepSeekClient, DeepSeekError


def _client(tmp_path: Path) -> DeepSeekClient:
    key_file = tmp_path / "deepseek-key"
    key_file.write_text("test-key", encoding="utf-8")
    return DeepSeekClient(key_file=key_file, base_url="https://example.invalid", model="test-model")


@patch("llm.deepseek.requests.post")
def test_complete_returns_content(mock_post, tmp_path):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    mock_post.return_value = response

    result = _client(tmp_path).complete("hello", json_mode=True)

    assert result == "ok"
    assert mock_post.call_args.kwargs["json"]["response_format"] == {"type": "json_object"}
    assert mock_post.call_args.kwargs["json"]["thinking"] == {"type": "disabled"}
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"


@patch("llm.deepseek.requests.post")
def test_complete_rejects_malformed_response(mock_post, tmp_path):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": []}
    mock_post.return_value = response

    with pytest.raises(DeepSeekError, match="invalid response"):
        _client(tmp_path).complete("hello")


@patch("llm.deepseek.requests.post")
def test_complete_handles_http_error_without_response_body(mock_post, tmp_path):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError("401 secret response")
    mock_post.return_value = response

    with pytest.raises(DeepSeekError, match="request failed") as exc_info:
        _client(tmp_path).complete("hello")
    assert "secret response" not in str(exc_info.value)


@patch("llm.deepseek.requests.post", side_effect=requests.Timeout("slow"))
def test_complete_handles_timeout(_mock_post, tmp_path):
    with pytest.raises(DeepSeekError, match="timed out"):
        _client(tmp_path).complete("hello")
