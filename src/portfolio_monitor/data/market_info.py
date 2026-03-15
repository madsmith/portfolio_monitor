from datetime import datetime, time, timedelta
import enum
from zoneinfo import ZoneInfo

from portfolio_monitor.service.types import AssetSymbol, AssetTypes

_UTC = ZoneInfo("UTC")
_EASTERN = ZoneInfo("America/New_York")
_MARKET_PRE_OPEN_TIME = time(4, 0)
_MARKET_OPEN_TIME = time(9, 30)
_MARKET_CLOSE_TIME = time(16, 0)
_MARKET_AFTER_CLOSE_TIME = time(20, 0)

class MarketStatus(enum.Enum):
    PRE_TRADING = "pre_trading"
    OPEN = "open"
    AFTER_TRADING = "after_trading"
    CLOSE = "close"

class MarketInfo:
    @classmethod
    def is_market_open(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> bool:
        """Return True if the market for *symbol* is open at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return True

        market_status = cls.get_market_status(symbol, at_time)
        return market_status in (MarketStatus.PRE_TRADING, MarketStatus.OPEN, MarketStatus.AFTER_TRADING)

    @classmethod
    def is_market_closed(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> bool:
        """Return True if the market for *symbol* is closed at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return False

        market_status = cls.get_market_status(symbol, at_time)
        return market_status == MarketStatus.CLOSE

    @classmethod
    def get_market_status(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> MarketStatus:
        """Return the current market status for *symbol* at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return MarketStatus.OPEN

        market_local_time = at_time.astimezone(_EASTERN)
        if market_local_time.weekday() >= 5:  # Saturday or Sunday
            return MarketStatus.CLOSE
        if market_local_time.time() < _MARKET_PRE_OPEN_TIME:
            return MarketStatus.CLOSE
        if _MARKET_PRE_OPEN_TIME <= market_local_time.time() < _MARKET_OPEN_TIME:
            return MarketStatus.PRE_TRADING
        if _MARKET_OPEN_TIME <= market_local_time.time() < _MARKET_CLOSE_TIME:
            return MarketStatus.OPEN
        if _MARKET_CLOSE_TIME <= market_local_time.time() < _MARKET_AFTER_CLOSE_TIME:
            return MarketStatus.AFTER_TRADING
        return MarketStatus.CLOSE

    @classmethod
    def is_market_pre_trading(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> bool:
        """Return True if the market for *symbol* is in pre-open phase at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return False

        market_status = cls.get_market_status(symbol, at_time)
        return market_status == MarketStatus.PRE_TRADING

    @classmethod
    def is_market_after_trading(cls, symbol: AssetSymbol, at_time: datetime | None = None) -> bool:
        """Return True if the market for *symbol* is in after-hours phase at *at_time*."""
        if at_time is None:
            at_time = datetime.now(tz=_UTC)

        if symbol.asset_type == AssetTypes.Crypto:
            return False

        market_status = cls.get_market_status(symbol, at_time)
        return market_status == MarketStatus.AFTER_TRADING

    @classmethod
    def get_market_open(cls, symbol: AssetSymbol, date: datetime) -> datetime:
        """Return the market open datetime for the session containing *date*.

        Crypto (24/7): 00:00:00.000 UTC on the same calendar day as *date*.
        Stocks / currencies: _MARKET_OPEN_TIME Eastern; weekend dates step back
        to the preceding Friday.
        """
        d = date.astimezone(_UTC).date()
        if symbol.asset_type == AssetTypes.Crypto:
            return datetime(d.year, d.month, d.day, tzinfo=_UTC)
        # Stocks and currencies — step back over weekends to the nearest trading day
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return datetime.combine(d, _MARKET_OPEN_TIME, tzinfo=_EASTERN)

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
    def get_market_hours(cls, symbol: AssetSymbol, date: datetime) -> dict[MarketStatus, datetime]:
        """Return the market hours for *symbol* on the given *date*."""
        if symbol.asset_type == AssetTypes.Crypto:
            return {
                MarketStatus.OPEN:          cls.get_market_open(symbol, date),
                MarketStatus.CLOSE:         cls.get_market_close(symbol, date),
            }
        else:
            open_time = cls.get_market_open(symbol, date)
            return {
                MarketStatus.PRE_TRADING:   datetime.combine(open_time.date(), _MARKET_PRE_OPEN_TIME, tzinfo=_EASTERN),
                MarketStatus.OPEN:          open_time,
                MarketStatus.AFTER_TRADING: datetime.combine(open_time.date(), _MARKET_AFTER_CLOSE_TIME, tzinfo=_EASTERN),
                MarketStatus.CLOSE:         datetime.combine(open_time.date(), _MARKET_CLOSE_TIME, tzinfo=_EASTERN),
            }

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
    def is_market_open_during(cls, symbol: AssetSymbol, from_: datetime, to: datetime) -> bool:
        """Return True if the market is open at any point in [from_, to).

        Open is defined as >= MARKET_OPEN_TIME and < MARKET_CLOSE_TIME (regular
        session only). Crypto is always open. *from_* and *to* must be
        timezone-aware.
        """
        if symbol.asset_type == AssetTypes.Crypto:
            return True

        from_eastern = from_.astimezone(_EASTERN)
        to_eastern = to.astimezone(_EASTERN)

        d = from_eastern.date()
        end_date = to_eastern.date()

        while d <= end_date:
            if d.weekday() < 5:  # Monday–Friday
                session_open = datetime.combine(d, _MARKET_OPEN_TIME, tzinfo=_EASTERN)
                session_close = datetime.combine(d, _MARKET_CLOSE_TIME, tzinfo=_EASTERN)
                if from_ < session_close and to > session_open:
                    return True
            d += timedelta(days=1)

        return False

    @classmethod
    def get_previous_market_close(cls, symbol: AssetSymbol, date: datetime) -> datetime:
        """Return the close datetime of the session immediately before *date*.

        Crypto: 23:59:59.999 UTC of the preceding calendar day.
        Stocks / currencies: _MARKET_CLOSE_TIME Eastern of the most recent trading
        day before the current session. The session boundary is _MARKET_PRE_OPEN_TIME
        (4AM): before 4AM the previous calendar day's session is still considered
        active, so the reference close does not flip until pre-market opens.
        """
        if symbol.asset_type == AssetTypes.Crypto:
            d = date.astimezone(_UTC).date() - timedelta(days=1)
            next_midnight = datetime(d.year, d.month, d.day, tzinfo=_UTC) + timedelta(days=1)
            return next_midnight - timedelta(milliseconds=1)

        dt = date.astimezone(_EASTERN)
        # Before pre-market open, we're still in the previous calendar day's session
        session_date = dt.date() if dt.time() >= _MARKET_PRE_OPEN_TIME else dt.date() - timedelta(days=1)
        candidate = session_date - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return datetime.combine(candidate, _MARKET_CLOSE_TIME, tzinfo=_EASTERN)
