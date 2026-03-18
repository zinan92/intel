"""Ticker extraction from article text."""
import re
from config import TICKER_ALIASES

_CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")

_ALIAS_LOOKUP: dict[str, str] = {}
for name, ticker in TICKER_ALIASES.items():
    _ALIAS_LOOKUP[name.upper()] = ticker
    if any("\u4e00" <= ch <= "\u9fff" for ch in name):
        _ALIAS_LOOKUP[name] = ticker


def extract_tickers(
    title: str | None,
    content: str | None,
    source_tickers: list[str] | None = None,
) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    title = title or ""
    content = (content or "")[:2000]
    text = f"{title} {content}"

    def _add(ticker: str) -> None:
        if ticker not in seen:
            seen.add(ticker)
            found.append(ticker)

    for match in _CASHTAG_RE.findall(text):
        _add(match)

    text_upper = text.upper()
    for alias, ticker in _ALIAS_LOOKUP.items():
        if any("\u4e00" <= ch <= "\u9fff" for ch in alias):
            if alias in text:
                _add(ticker)
        else:
            if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text_upper):
                _add(ticker)

    if source_tickers:
        for ticker in source_tickers:
            _add(ticker)

    return found
