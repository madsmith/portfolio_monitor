import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def parse_period(period: str) -> timedelta:
    """
    Parse the period string into a timedelta.
    """
    if period.endswith("d"):
        return timedelta(days=int(period[:-1]))
    elif period.endswith("h"):
        return timedelta(hours=int(period[:-1]))
    elif period.endswith("m"):
        return timedelta(minutes=int(period[:-1]))
    elif period.endswith("s"):
        return timedelta(seconds=int(period[:-1]))
    else:
        raise ValueError(f"Invalid period: {period}")


def datetime_from_ms(ms: int, tz: ZoneInfo) -> datetime:
    assert tz is not None, "Timezone must be specified"

    return datetime.fromtimestamp(ms / 1000, tz)


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