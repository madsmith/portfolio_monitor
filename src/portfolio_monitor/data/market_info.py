from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.service.types import AssetSymbol, AssetTypes

_UTC = ZoneInfo("UTC")
_EASTERN = ZoneInfo("America/New_York")


class MarketInfo:
    @classmethod
    def get_previous_close_datetime(cls) -> datetime:
        """Return the datetime of the most recent market close (4:00 PM Eastern)."""
        now: datetime = datetime.now(tz=_EASTERN)
        market_close_time = time(16, 0)

        if now.weekday() < 5 and now.time() >= market_close_time:
            return datetime.combine(now.date(), market_close_time, tzinfo=_EASTERN)

        if now.weekday() == 0:
            base_date = now.date() - timedelta(days=3)
        elif now.weekday() == 6:
            base_date = now.date() - timedelta(days=2)
        else:
            base_date = now.date() - timedelta(days=1)

        return datetime.combine(base_date, market_close_time, tzinfo=_EASTERN)

    @classmethod
    def get_market_close(cls, symbol: AssetSymbol, date: datetime) -> datetime:
        """Return the market close datetime for the session containing *date*.

        Crypto (24/7): 23:59:59.999 UTC on the same calendar day as *date*.
        Stocks / currencies: 21:00:00 UTC; weekend dates step back to the
        preceding Friday.
        """
        d = date.astimezone(_UTC).date()
        if symbol.asset_type == AssetTypes.Crypto:
            next_midnight = datetime(d.year, d.month, d.day, tzinfo=_UTC) + timedelta(days=1)
            return next_midnight - timedelta(milliseconds=1)
        # Stocks and currencies — step back over weekends to the nearest trading day
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return datetime.combine(d, time(21, 0, 0), tzinfo=_UTC)

    @classmethod
    def get_market_day_timespan(cls, symbol: AssetSymbol) -> timedelta:
        """Return the duration of one trading session for *symbol*.

        Crypto (24/7): 24 hours.
        Stocks / currencies: 6 hours 30 minutes (9:30 AM – 4:00 PM ET).
        """
        if symbol.asset_type == AssetTypes.Crypto:
            return timedelta(hours=24)
        return timedelta(hours=6, minutes=30)

    @classmethod
    def get_previous_market_close(cls, symbol: AssetSymbol, date: datetime) -> datetime:
        """Return the close datetime of the session immediately before *date*.

        Crypto: 23:59:59.999 UTC of the preceding calendar day.
        Stocks / currencies: the most recent 21:00:00 UTC strictly before *date*,
        skipping weekends.
        """
        if symbol.asset_type == AssetTypes.Crypto:
            d = date.astimezone(_UTC).date() - timedelta(days=1)
            next_midnight = datetime(d.year, d.month, d.day, tzinfo=_UTC) + timedelta(days=1)
            return next_midnight - timedelta(milliseconds=1)

        dt = date.astimezone(_UTC)
        d = dt.date()
        close_today = datetime.combine(d, time(21, 0, 0), tzinfo=_UTC)

        # If we're strictly past today's close, today's close is the previous close
        candidate = d if dt > close_today else d - timedelta(days=1)
        # Step back over weekends
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return datetime.combine(candidate, time(21, 0, 0), tzinfo=_UTC)
