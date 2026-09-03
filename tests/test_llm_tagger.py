from unittest.mock import Mock

import pytest

from llm.deepseek import DeepSeekError
from tagging.llm import LLMTagger, TaggingError


def _articles():
    return [{"id": 7, "title": "Fed decision", "content": "Rates changed", "source": "rss"}]


def test_tagger_uses_deepseek_and_preserves_contract():
    client = Mock()
    client.complete.return_value = '{"results":[{"id":7,"relevance_score":5,"narrative_tags":["fed-rate-shock"]}]}'
    fallback = Mock()

    result = LLMTagger(client=client, fallback_client=fallback).tag_batch(_articles())

    assert result.items == ({"id": 7, "relevance_score": 5, "narrative_tags": ["fed-rate-shock"]},)
    assert result.provider == "deepseek"
    assert result.fallback_reason is None
    assert client.complete.call_args.kwargs["json_mode"] is True
    fallback.complete.assert_not_called()


def test_tagger_falls_back_after_malformed_deepseek_json():
    client = Mock()
    client.complete.return_value = "not json"
    fallback = Mock()
    fallback.complete.return_value = '{"results":[{"id":7,"relevance_score":4,"narrative_tags":["fed-policy"]}]}'

    result = LLMTagger(client=client, fallback_client=fallback).tag_batch(_articles())

    assert result.provider == "codex-cli"
    assert result.fallback_reason == "invalid_primary_output"
    assert result.items[0]["relevance_score"] == 4


def test_tagger_falls_back_after_deepseek_error():
    client = Mock()
    client.complete.side_effect = DeepSeekError("request failed")
    fallback = Mock()
    fallback.complete.return_value = '{"results":[{"id":7,"relevance_score":3,"narrative_tags":["fed-decision"]}]}'

    result = LLMTagger(client=client, fallback_client=fallback).tag_batch(_articles())

    assert result.provider == "codex-cli"
    assert result.fallback_reason == "DeepSeekError"
    assert result.items[0]["relevance_score"] == 3


def test_tagger_raises_when_both_providers_fail():
    client = Mock()
    client.complete.side_effect = DeepSeekError("request failed")
    fallback = Mock()
    fallback.complete.side_effect = RuntimeError("fallback failed")

    with pytest.raises(TaggingError, match="both providers failed"):
        LLMTagger(client=client, fallback_client=fallback).tag_batch(_articles())


def test_tagger_rejects_partial_result_set():
    client = Mock()
    client.complete.return_value = '{"results":[]}'
    fallback = Mock()
    fallback.complete.return_value = '{"results":[]}'

    with pytest.raises(TaggingError, match="both providers failed"):
        LLMTagger(client=client, fallback_client=fallback).tag_batch(_articles())
