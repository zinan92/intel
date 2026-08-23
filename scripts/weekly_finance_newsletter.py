"""Generate a side-effect-free Weekly Finance retrospective dry-run."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.generate_narrative_signal import _call_deepseek


DEFAULT_ARCHIVE_DIR = Path("/Users/wendy/park-io/007_finance daily newsletter")
MAX_WEEKLY_MARKDOWN_CHARS = 3600
_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:[$¥€]\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.\d+)?(?:%|[KMBT]|\s*(?:million|billion|trillion|万亿|亿))?"
    r"(?![A-Za-z])",
    re.I,
)
_REQUIRED_THEME_FIELDS = (
    "title",
    "summary",
    "causal_chain",
    "confirmation_signal",
    "invalidation_signal",
    "source_refs",
)


@dataclass(frozen=True)
class WeeklyWindow:
    week_ending: date
    lookback_start: date
    lookback_end: date
    watch_start: date
    watch_end: date


@dataclass(frozen=True)
class DailyArchive:
    day: date
    path: Path
    input_id: str
    content: str


@dataclass(frozen=True)
class WeeklyArchives:
    window: WeeklyWindow
    archives: tuple[DailyArchive, ...]
    missing_days: tuple[date, ...]
    coverage_status: str

    @property
    def daily_count(self) -> int:
        return len(self.archives)


@dataclass(frozen=True)
class WeeklyDryRunResult:
    window: WeeklyWindow
    coverage_status: str
    daily_count: int
    provider: str
    draft: dict[str, Any]
    markdown: str


@dataclass(frozen=True)
class WeeklyValidation:
    passed: bool
    issues: tuple[str, ...]


class WeeklyGenerationError(RuntimeError):
    """Raised when a Weekly dry-run cannot meet its publication contract."""


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def weekly_window(week_ending: date | str) -> WeeklyWindow:
    end = _as_date(week_ending)
    if end.weekday() != 6:
        raise ValueError("week_ending must be a Sunday")
    start = end - timedelta(days=6)
    return WeeklyWindow(
        week_ending=end,
        lookback_start=start,
        lookback_end=end,
        watch_start=end + timedelta(days=1),
        watch_end=end + timedelta(days=7),
    )


def load_weekly_archives(week_ending: date | str, archive_dir: Path = DEFAULT_ARCHIVE_DIR) -> WeeklyArchives:
    window = weekly_window(week_ending)
    archives: list[DailyArchive] = []
    missing: list[date] = []
    for offset in range(7):
        day = window.lookback_start + timedelta(days=offset)
        path = archive_dir / f"{day.isoformat()}-finance-daily-newsletter.md"
        if not path.exists():
            missing.append(day)
            continue
        archives.append(
            DailyArchive(
                day=day,
                path=path,
                input_id=f"daily:{day.isoformat()}",
                content=path.read_text(encoding="utf-8"),
            )
        )

    count = len(archives)
    status = "complete" if count == 7 else "degraded" if count >= 5 else "insufficient"
    return WeeklyArchives(window, tuple(archives), tuple(missing), status)


def _prompt(bundle: WeeklyArchives) -> str:
    daily_inputs = "\n\n".join(
        f"INPUT {archive.input_id} ({archive.day.isoformat()})\n{archive.content[:12000]}"
        for archive in bundle.archives
    )
    return f"""You are the synthesis stage of a Weekly Finance Newsletter pipeline.
You do not browse, call APIs, or invent source data. Use only the Daily archive inputs below.

Lookback: {bundle.window.lookback_start} through {bundle.window.lookback_end}
Coverage: {bundle.coverage_status} ({bundle.daily_count}/7)

Return JSON only with this shape:
{{
  "lookback_themes": [
    {{
      "title": "short theme",
      "summary": "what happened; preserve source numbers exactly",
      "causal_chain": "why it mattered",
      "affected_assets": ["ticker or asset"],
      "confirmation_signal": "what confirms continuation",
      "invalidation_signal": "what breaks the thesis",
      "source_refs": ["daily:YYYY-MM-DD"]
    }}
  ],
  "source_health": "reader-facing coverage statement"
}}

Rules:
- Produce 2 to 4 non-duplicated themes.
- Keep the complete rendered report within one page; be concise and omit low-value detail.
- Write all reader-facing prose in Chinese; keep tickers and standard technical terms in English.
- Every theme must cite one or more supplied source_refs.
- Copy prices, percentages, dates, and other numeric values exactly from inputs.
- If a numeric claim is not necessary or cannot be copied exactly, omit it.
- Do not convert Chinese units such as 亿 into B/M or otherwise normalize a displayed number.
- Do not turn a forecast, target, or scenario into a completed fact.
- Do not include database fields, source identifiers, or collection metrics in prose.
- The next-week calendar is not connected in this milestone; do not invent watch events.

Daily archive inputs:
{daily_inputs}
"""


def _repair_prompt(
    original_prompt: str,
    draft: dict[str, Any],
    issues: tuple[str, ...],
    source_text: dict[str, str],
) -> str:
    return f"""Repair the JSON weekly draft below. Return JSON only.

Quality gate errors:
{chr(10).join(f'- {issue}' for issue in issues)}

Do not invent, convert, round, or restate numeric values. Remove a numeric claim
when it cannot be copied exactly from the source excerpts. Keep source_refs
unchanged and keep the required JSON shape.
If the errors mention length, return exactly 2 or 3 themes and keep every text
field short enough for the rendered Markdown to remain under 3600 characters.

Original draft:
{json.dumps(draft, ensure_ascii=False)}

Source excerpts:
{chr(10).join(f'{key}: {value[:4000]}' for key, value in source_text.items())}

The original task constraints were:
{original_prompt}
"""


def _parse_json(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise WeeklyGenerationError("DeepSeek did not return a JSON weekly draft")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise WeeklyGenerationError("DeepSeek returned malformed weekly JSON") from exc
    if not isinstance(parsed, dict):
        raise WeeklyGenerationError("DeepSeek weekly draft must be a JSON object")
    return parsed


def _all_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_all_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_all_text(v) for v in value)
    return str(value)


def _normalized_numbers(text: str) -> set[tuple[str, Decimal]]:
    values: set[tuple[str, Decimal]] = set()
    multipliers = {
        "K": Decimal("1000"),
        "M": Decimal("1000000"),
        "B": Decimal("1000000000"),
        "T": Decimal("1000000000000"),
        "million": Decimal("1000000"),
        "billion": Decimal("1000000000"),
        "trillion": Decimal("1000000000000"),
        "万亿": Decimal("1000000000000"),
        "亿": Decimal("100000000"),
    }
    for match in _NUMBER_PATTERN.finditer(text):
        raw = match.group(0).replace(",", "").replace(" ", "")
        prefix = raw[0] if raw and raw[0] in "$¥€" else ""
        numeric = raw[1:] if prefix else raw
        suffix = ""
        for candidate in ("trillion", "billion", "million", "万亿", "亿"):
            if numeric.lower().endswith(candidate):
                suffix = candidate
                numeric = numeric[: -len(candidate)]
                break
        if not suffix and numeric and numeric[-1].upper() in {"K", "M", "B", "T"}:
            suffix = numeric[-1].upper()
            numeric = numeric[:-1]
        unit = "%" if numeric.endswith("%") else "number"
        if numeric.endswith("%"):
            numeric = numeric[:-1]
        try:
            value = Decimal(numeric) * multipliers.get(suffix, Decimal("1"))
        except Exception:
            continue
        values.add((unit, value))
    return values


def validate_weekly_draft(draft: dict[str, Any], source_text: dict[str, str]) -> WeeklyValidation:
    issues: list[str] = []
    themes = draft.get("lookback_themes")
    if not isinstance(themes, list) or not 2 <= len(themes) <= 4:
        issues.append("weekly draft must contain 2-4 themes")
        themes = themes if isinstance(themes, list) else []

    titles: set[str] = set()
    canonical_numbers = _normalized_numbers(" ".join(source_text.values()))
    for index, theme in enumerate(themes):
        if not isinstance(theme, dict):
            issues.append(f"theme {index + 1} is not an object")
            continue
        missing = [field for field in _REQUIRED_THEME_FIELDS if not theme.get(field)]
        if missing:
            issues.append(f"theme {index + 1} missing fields: {', '.join(missing)}")
        title = str(theme.get("title", "")).strip().lower()
        if title and title in titles:
            issues.append(f"duplicate theme title: {title}")
        titles.add(title)
        refs = theme.get("source_refs") or []
        unknown = [ref for ref in refs if ref not in source_text]
        if unknown:
            issues.append(f"theme {index + 1} has unknown source refs: {', '.join(unknown)}")
        numeric_theme = {key: value for key, value in theme.items() if key != "source_refs"}
        output_numbers = _normalized_numbers(_all_text(numeric_theme))
        ungrounded = sorted(output_numbers - canonical_numbers)
        if ungrounded:
            formatted = ", ".join(f"{unit}{value}" for unit, value in ungrounded)
            issues.append(f"theme {index + 1} has ungrounded numeric claims: {formatted}")

    source_health = str(draft.get("source_health", ""))
    if not source_health.strip():
        issues.append("weekly draft is missing source health")
    return WeeklyValidation(passed=not issues, issues=tuple(issues))


def render_weekly_markdown(draft: dict[str, Any], bundle: WeeklyArchives) -> str:
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "---",
        f"title: Weekly Finance Newsletter {bundle.window.week_ending.isoformat()}",
        f"week_ending: {bundle.window.week_ending.isoformat()}",
        f"lookback: {bundle.window.lookback_start.isoformat()}/{bundle.window.lookback_end.isoformat()}",
        f"watch_window: {bundle.window.watch_start.isoformat()}/{bundle.window.watch_end.isoformat()}",
        f"daily_count: {bundle.daily_count}/7",
        f"coverage_status: {bundle.coverage_status}",
        f"generated_at: {generated_at}",
        "source: park-intel",
        "---",
        "",
        f"# Weekly Finance Newsletter | {bundle.window.week_ending.isoformat()}",
        "",
        "## What happened last week",
        "",
    ]
    for index, theme in enumerate(draft["lookback_themes"], 1):
        lines.extend(
            [
                f"**{index}. {theme['title']}**",
                str(theme["summary"]),
                f"因果链：{theme['causal_chain']}",
                f"相关资产：{', '.join(str(item) for item in theme.get('affected_assets', []))}",
                f"确认信号：{theme['confirmation_signal']}",
                f"证伪信号：{theme['invalidation_signal']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Things to watch for next week",
            "",
            "### Macro & international events",
            "",
            "- Calendar discovery is not connected in this milestone; no events are asserted.",
            "",
            "### Major earnings",
            "",
            "- Earnings discovery is not connected in this milestone; no earnings are asserted.",
            "",
            "## Source Status",
            "",
            f"- Daily archives: {bundle.coverage_status} ({bundle.daily_count}/7).",
            f"- Weekly lookback: {bundle.window.lookback_start.isoformat()} through {bundle.window.lookback_end.isoformat()}.",
            f"- Calendar and earnings discovery: not connected in this milestone.",
            "- Synthesis: bounded DeepSeek draft; weekly facts are rendered from validated Daily inputs.",
            "",
            "This is a trading research brief, not investment advice.",
        ]
    )
    return "\n".join(lines) + "\n"


def generate_weekly_dry_run(
    week_ending: date | str,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
) -> WeeklyDryRunResult:
    bundle = load_weekly_archives(week_ending, archive_dir)
    if bundle.coverage_status == "insufficient":
        raise WeeklyGenerationError(
            f"insufficient Daily Newsletter coverage: {bundle.daily_count}/7"
        )
    prompt = _prompt(bundle)
    content, provider = _call_deepseek(prompt)
    if not content:
        raise WeeklyGenerationError("weekly synthesis returned no content")
    source_text = {archive.input_id: archive.content for archive in bundle.archives}
    markdown = ""
    for attempt in range(2):
        draft = _parse_json(content)
        validation = validate_weekly_draft(draft, source_text)
        if validation.passed:
            markdown = render_weekly_markdown(draft, bundle)
            if len(markdown) <= MAX_WEEKLY_MARKDOWN_CHARS:
                break
            validation = WeeklyValidation(
                passed=False,
                issues=(
                    f"rendered weekly brief exceeds length limit: {len(markdown)} > {MAX_WEEKLY_MARKDOWN_CHARS}",
                ),
            )
        if attempt == 1:
            raise WeeklyGenerationError("weekly quality gate failed: " + "; ".join(validation.issues))
        content, repair_provider = _call_deepseek(
            _repair_prompt(prompt, draft, validation.issues, source_text)
        )
        if not content:
            raise WeeklyGenerationError("weekly synthesis repair returned no content")
        provider = f"{provider}+repair:{repair_provider or 'unknown'}"
    return WeeklyDryRunResult(
        window=bundle.window,
        coverage_status=bundle.coverage_status,
        daily_count=bundle.daily_count,
        provider=provider or "unknown",
        draft=draft,
        markdown=markdown,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Weekly Finance retrospective dry-run")
    parser.add_argument("--week-ending", required=True, help="Sunday in YYYY-MM-DD")
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("this milestone only supports --dry-run")
    result = generate_weekly_dry_run(args.week_ending, args.archive_dir)
    print(f"weekly_dry_run: pass provider={result.provider} coverage={result.coverage_status}")
    print(result.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
