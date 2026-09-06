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


@patch('llm.deepseek.requests.post')
def test_billing_failure_pauses_repeated_requests_and_recovers(mock_post, tmp_path, monkeypatch):
    import llm.deepseek as mod
    clock = [100.0]
    monkeypatch.setattr(mod.time, 'monotonic', lambda: clock[0])
    client = _client(tmp_path)
    response = requests.Response()
    response.status_code = 402
    mock_post.return_value = response
    with pytest.raises(mod.DeepSeekBillingError, match='402'):
        client.complete('probe')
    with pytest.raises(mod.DeepSeekBillingError, match='paused'):
        client.complete('probe')
    assert mock_post.call_count == 1
    assert mod.provider_health()['status'] == 'insufficient_balance'
    clock[0] += 901
    ok = Mock()
    ok.json.return_value = {'choices': [{'message': {'content': 'ok'}}]}
    mock_post.return_value = ok
    assert client.complete('probe') == 'ok'
    assert mod.provider_health()['status'] == 'ok'
