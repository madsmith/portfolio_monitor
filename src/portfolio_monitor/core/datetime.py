import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Matches "NNunit" where unit is one of: mo, s, m, h, d, w (case-insensitive)
_PERIOD_RE = re.compile(r"^(\d+)(mo|[smhdwy])$", re.IGNORECASE)


def parse_period_parts(period: str) -> tuple[int, str]:
    """Parse a period string into (multiplier, normalized_suffix).

    Normalized suffix is always lowercase: s, m, h, d, w, mo.
    Supports: s (seconds), m (minutes), h (hours), d (days), w (weeks), mo (months).
    Case-insensitive — '1H' and '1h' are equivalent.

    Raises ValueError for unrecognised formats.
    """
    m = _PERIOD_RE.fullmatch(period.strip())
    if m is None:
        raise ValueError(
            f"invalid period {period!r}; "
            "expected format like '1m', '5m', '1H', '1d', '1w', '1mo'"
        )
    return int(m.group(1)), m.group(2).lower()


def parse_period(period: str) -> timedelta:
    """Parse a period string into a timedelta.

    Supports: s (seconds), m (minutes), h (hours), d (days), w (weeks), mo (~30 days).
    Case-insensitive — '1H' and '1h' are equivalent.
    """
    n, unit = parse_period_parts(period)
    match unit:
        case "s":  return timedelta(seconds=n)
        case "m":  return timedelta(minutes=n)
        case "h":  return timedelta(hours=n)
        case "d":  return timedelta(days=n)
        case "w":  return timedelta(weeks=n)
        case "mo": return timedelta(days=n * 30)
        case "y":  return timedelta(days=n * 365)
        case _:    raise ValueError(f"unsupported unit: {unit!r}")


def datetime_from_ms(ms: int, tz: ZoneInfo) -> datetime:
    assert tz is not None, "Timezone must be specified"

    return datetime.fromtimestamp(ms / 1000, tz)


def ms_from_datetime(dt: datetime) -> int:
    """
    Convert datetime to milliseconds since epoch, ensuring datetime is timezone aware
    and converting to UTC first.
    """
    if dt.tzinfo is None:
        raise ValueError(f"Datetime must be timezone-aware. Got: {dt}")

    # Convert to UTC if not already
    utc_dt = dt.astimezone(ZoneInfo("UTC"))

    return int(utc_dt.timestamp() * 1000)


def parse_date(value: str) -> datetime | None:
    """Parse a date/time reference string.

    Priority order:
    1. ISO 8601 datetime (contains 'T', e.g. "2025-01-15T14:30:00+00:00")
    2. str(datetime) format (e.g. "2025-01-15 14:30:00.123456")
    3. Unix timestamp as numeric string (e.g. "1705328400" or "1705328400.5")
       — returned as UTC-aware datetime
    4. Date-only formats (YYYY-MM-DD, MM/DD/YYYY, etc.)
       — returned as naive datetime
    """
    if not value or not isinstance(value, str):
        return None
    value = value.strip()

    # 1. ISO 8601 datetime (T separator)
    if "T" in value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass

    # 2. str(datetime): "YYYY-MM-DD HH:MM:SS[.ffffff]"
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    # 3. Unix timestamp (numeric string)
    try:
        ts = float(value)
        if ts > 0:
            return datetime.fromtimestamp(ts, tz=ZoneInfo("UTC"))
    except ValueError:
        pass

    # 4. Date-only patterns
    patterns = [
        (r"^\d{4}-\d{1,2}-\d{1,2}$", "%Y-%m-%d"),
        (r"^\d{4}/\d{1,2}/\d{1,2}$", "%Y/%m/%d"),
        (r"^\d{4}\.\d{1,2}\.\d{1,2}$", "%Y.%m.%d"),
        (r"^\d{1,2}/\d{1,2}/\d{4}$", "%m/%d/%Y"),
        (r"^\d{1,2}/\d{1,2}/\d{4}$", "%d/%m/%Y"),
        (r"^\d{1,2}-\d{1,2}-\d{4}$", "%m-%d-%Y"),
        (r"^\d{1,2}-\d{1,2}-\d{4}$", "%d-%m-%Y"),
        (r"^\d{1,2}\.\d{1,2}\.\d{4}$", "%m.%d.%Y"),
        (r"^\d{1,2}\.\d{1,2}\.\d{4}$", "%d.%m.%Y"),
        (r"^\d{1,2}/\d{1,2}/\d{2} \d{2}:\d{2}:\d{2}$", "%m/%d/%y %H:%M:%S"),
        (r"^\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}:\d{2}$", "%m/%d/%Y %H:%M:%S"),
    ]
    for pattern, fmt in patterns:
        if re.match(pattern, value):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

    logger.warning("Could not parse date '%s' with any known format", value)
    return None