from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


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