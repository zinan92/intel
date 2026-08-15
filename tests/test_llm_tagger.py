from unittest.mock import Mock

from llm.deepseek import DeepSeekError
from tagging.llm import LLMTagger


def _articles():
    return [{"id": 7, "title": "Fed decision", "content": "Rates changed", "source": "rss"}]


def test_tagger_uses_deepseek_and_preserves_contract():
    client = Mock()
    client.complete.return_value = '{"results":[{"id":7,"relevance_score":5,"narrative_tags":["fed-rate-shock"]}]}'

    result = LLMTagger(client=client).tag_batch(_articles())

    assert result == [{"id": 7, "relevance_score": 5, "narrative_tags": ["fed-rate-shock"]}]
    assert client.complete.call_args.kwargs["json_mode"] is True


def test_tagger_rejects_malformed_json():
    client = Mock()
    client.complete.return_value = "not json"
    assert LLMTagger(client=client).tag_batch(_articles()) == []


def test_tagger_handles_deepseek_error():
    client = Mock()
    client.complete.side_effect = DeepSeekError("request failed")
    assert LLMTagger(client=client).tag_batch(_articles()) == []
