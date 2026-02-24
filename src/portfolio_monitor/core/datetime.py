from datetime import timedelta


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
