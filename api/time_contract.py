"""Wire-format contract for UTC timestamps stored as naive SQLite datetimes."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_rfc3339(value: datetime | str | None) -> str | None:
    """Serialize a project timestamp as an unambiguous RFC3339 UTC instant."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        parsed = value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")
