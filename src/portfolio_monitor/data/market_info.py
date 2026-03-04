from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.service.types import AssetSymbol, AssetTypes

_UTC = ZoneInfo("UTC")
_EASTERN = ZoneInfo("America/New_York")
_MARKET_PRE_OPEN_TIME = time(4, 0)
_MARKET_OPEN_TIME = time(9, 30)
_MARKET_CLOSE_TIME = time(16, 0)
_MARKET_AFTER_CLOSE_TIME = time(20, 0)

class MarketInfo:
    @classmethod
    def is_market_open(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> bool:
        """Return True if the market for *symbol* is open at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return True

        local_time = at_time.astimezone(_EASTERN)
        if local_time.weekday() >= 5:  # Saturday or Sunday
            return False

        return _MARKET_PRE_OPEN_TIME <= local_time.time() < _MARKET_AFTER_CLOSE_TIME

    @classmethod
    def is_market_pre_trading(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> bool:
        """Return True if the market for *symbol* is in pre-open phase at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return False

        local_time = at_time.astimezone(_EASTERN)
        if local_time.weekday() >= 5:  # Saturday or Sunday
            return False

        return _MARKET_PRE_OPEN_TIME <= local_time.time() < _MARKET_OPEN_TIME

    @classmethod
    def is_market_after_trading(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> bool:
        """Return True if the market for *symbol* is in after-hours phase at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return False

        local_time = at_time.astimezone(_EASTERN)
        if local_time.weekday() >= 5:  # Saturday or Sunday
            return False

        return _MARKET_CLOSE_TIME <= local_time.time() < _MARKET_AFTER_CLOSE_TIME

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
        Stocks / currencies: _MARKET_CLOSE_TIME Eastern; weekend dates step back
        to the preceding Friday.
        """
        d = date.astimezone(_UTC).date()
        if symbol.asset_type == AssetTypes.Crypto:
            next_midnight = datetime(d.year, d.month, d.day, tzinfo=_UTC) + timedelta(days=1)
            return next_midnight - timedelta(milliseconds=1)
        # Stocks and currencies — step back over weekends to the nearest trading day
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return datetime.combine(d, _MARKET_CLOSE_TIME, tzinfo=_EASTERN)

    @classmethod
    def get_market_day_timespan(cls, symbol: AssetSymbol) -> timedelta:
        """Return the duration of one trading session for *symbol*.

        Crypto (24/7): 24 hours.
        Stocks / currencies: span from _MARKET_PRE_OPEN_TIME to _MARKET_AFTER_CLOSE_TIME.
        """
        if symbol.asset_type == AssetTypes.Crypto:
            return timedelta(hours=24)
        return (
            timedelta(hours=_MARKET_AFTER_CLOSE_TIME.hour, minutes=_MARKET_AFTER_CLOSE_TIME.minute)
            - timedelta(hours=_MARKET_PRE_OPEN_TIME.hour, minutes=_MARKET_PRE_OPEN_TIME.minute)
        )

    @classmethod
    def get_previous_market_close(cls, symbol: AssetSymbol, date: datetime) -> datetime:
        """Return the close datetime of the session immediately before *date*.

        Crypto: 23:59:59.999 UTC of the preceding calendar day.
        Stocks / currencies: the most recent _MARKET_CLOSE_TIME Eastern strictly
        before *date*, skipping weekends.
        """
        if symbol.asset_type == AssetTypes.Crypto:
            d = date.astimezone(_UTC).date() - timedelta(days=1)
            next_midnight = datetime(d.year, d.month, d.day, tzinfo=_UTC) + timedelta(days=1)
            return next_midnight - timedelta(milliseconds=1)

        dt = date.astimezone(_EASTERN)
        d = dt.date()
        close_today = datetime.combine(d, _MARKET_CLOSE_TIME, tzinfo=_EASTERN)

        # If we're strictly past today's close, today's close is the previous close
        candidate = d if dt > close_today else d - timedelta(days=1)
        # Step back over weekends
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return datetime.combine(candidate, _MARKET_CLOSE_TIME, tzinfo=_EASTERN)
