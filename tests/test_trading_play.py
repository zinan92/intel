"""Tests for trading play parsing."""


def test_parse_response_with_scenarios():
    from events.narrator import _parse_narrator_response
    response = """SUMMARY: Bitcoin ETFs saw record inflows.

SCENARIO A: If inflows continue, BTC could test $75K. Consider long BTC.

SCENARIO B: If inflows reverse, consider reducing exposure."""
    summary, play = _parse_narrator_response(response)
    assert "Bitcoin ETFs" in summary
    assert "SCENARIO A" in play
    assert "SCENARIO B" in play


def test_parse_response_without_scenarios():
    from events.narrator import _parse_narrator_response
    response = "Bitcoin ETFs saw record inflows. Bullish."
    summary, play = _parse_narrator_response(response)
    assert summary == response
    assert play is None


def test_parse_response_empty():
    from events.narrator import _parse_narrator_response
    summary, play = _parse_narrator_response("")
    assert summary == ""
    assert play is None


def test_parse_response_with_probabilities():
    from events.narrator import _parse_narrator_response

    response = """SUMMARY: Bitcoin ETFs saw record inflows.

BULL_PCT: 65
BULL: If inflows continue above $500M daily, BTC tests $75K. Consider long BTC.

BEAR_PCT: 35
BEAR: If inflows reverse, this was anomaly. Consider reducing exposure."""

    summary, play = _parse_narrator_response(response)
    assert "Bitcoin ETFs" in summary
    assert "BULL_PCT" in play
    assert "65" in play
    assert "BEAR_PCT" in play
    assert "35" in play
