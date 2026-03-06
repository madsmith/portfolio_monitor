from datetime import datetime
from zoneinfo import ZoneInfo


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