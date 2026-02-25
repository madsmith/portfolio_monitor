from datetime import datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo


class MarketInfo:
    @classmethod
    def get_previous_close_datetime(cls) -> datetime:
        """Return the datetime of the most recent market close (4:00 PM Eastern)."""
        eastern: ZoneInfo = ZoneInfo("America/New_York")
        now: datetime = datetime.now(tz=eastern)
        market_close_time: dtime = dtime(16, 0)

        if now.weekday() < 5 and now.time() >= market_close_time:
            return datetime.combine(now.date(), market_close_time, tzinfo=eastern)

        if now.weekday() == 0:
            base_date = now.date() - timedelta(days=3)
        elif now.weekday() == 6:
            base_date = now.date() - timedelta(days=2)
        else:
            base_date = now.date() - timedelta(days=1)

        return datetime.combine(base_date, market_close_time, tzinfo=eastern)
