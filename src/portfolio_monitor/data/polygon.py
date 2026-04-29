import asyncio
from datetime import datetime, timedelta

import logfire
from zoneinfo import ZoneInfo

from polygon import RESTClient as PolygonRESTClient
from polygon.rest.aggs import Agg, DailyOpenCloseAgg
from urllib3 import HTTPResponse
from urllib3.exceptions import RequestError

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core import eastern_midnight
from portfolio_monitor.data.aggregate_cache import (
    Aggregate,
    AggregateCache,
    DailyOpenCloseAggregate,
)
from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.data.timespan import AggregateTimespan
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.utils import get_trace_logger, logfire_set_attribute

logger = get_trace_logger(__name__)

type DateRange = tuple[datetime, datetime]


class PolygonDataProvider(DataProvider):
    """Provider for fetching aggregate data from Polygon with cache-first approach."""

    def __init__(self, config: PortfolioMonitorConfig, aggregate_cache: AggregateCache):
        """
        Initialize the data provider with configuration and cache

        Args:
            config: Application configuration with Polygon API settings
            aggregate_cache: Cache for storing/retrieving aggregates
        """
        self._config: PortfolioMonitorConfig = config
        self._aggregate_cache: AggregateCache = aggregate_cache

        # Time delay before considering data not real-time (default 15 minutes)
        # Add a 1-minute margin to the configured delay to ensure we're getting truly fresh data
        base_delay = timedelta(seconds=config.polygon_delay)
        self._delay: timedelta = base_delay
        self._polygon_client: PolygonRESTClient = PolygonRESTClient(
            config.polygon_api_key
        )
        self._rate_limit_sleep: float = 12.1  # Sleep time when rate limited (slightly over 12 seconds per Polygon docs)
        self._max_retries: int = 5

    @logfire.instrument("polygon.get_aggregate {symbol.ticker}")
    async def get_aggregate(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None:
        """
        Get the most recent aggregate for a ticker

        Args:
            symbol: Ticker symbol to fetch data for

        Returns:
            Most recent Aggregate or None if not available
        """
        # Try to get from cache first
        current: Aggregate | None = self._aggregate_cache.get_current(symbol)
        now: datetime = datetime.now(ZoneInfo("UTC"))

        # Check if we have recent data in cache
        if current and (now - current.date_open) < self._delay:
            logger.debug("Fetching aggregate for %s from cache", symbol)
            logfire_set_attribute("source", "cache")
            return current

        logfire_set_attribute("source", "api")
        # Otherwise fetch from API
        try:
            # Get the most recent 1-minute bar
            to_time = now
            from_time = now - timedelta(minutes=1)

            aggs = None
            for attempt in range(self._max_retries):
                try:
                    logger.debug("Fetching aggregate for %s from API (attempt %d)", symbol, attempt + 1)
                    with logfire.span("polygon.api.get_aggs {symbol.ticker}", symbol=symbol):
                        aggs = self._polygon_client.get_aggs(
                            ticker=symbol.lookup_symbol,
                            multiplier=1,
                            timespan="minute",
                            from_=from_time,
                            to=to_time,
                            limit=1,
                        )
                    break
                except RequestError:
                    if attempt < self._max_retries - 1:
                        logger.warning(
                            f"Rate limit hit for {symbol}, waiting {self._rate_limit_sleep} seconds"
                        )
                        await asyncio.sleep(self._rate_limit_sleep)
                    else:
                        raise

            if aggs and isinstance(aggs, list) and len(aggs) > 0:
                last_aggregate = None
                for agg in aggs:
                    if (
                        agg.timestamp is not None
                        and agg.open is not None
                        and agg.high is not None
                        and agg.low is not None
                        and agg.close is not None
                        and agg.volume is not None
                    ):
                        timestamp = _polygon_timestamp_to_datetime(agg.timestamp)
                        aggregate = Aggregate(
                            symbol,
                            timestamp,
                            agg.open,
                            agg.high,
                            agg.low,
                            agg.close,
                            agg.volume,
                            timedelta(minutes=1),
                        )
                        if cache_write:
                            logger.debug("Caching aggregate for %s: %s", symbol, aggregate)
                            await self._aggregate_cache.add(aggregate)
                        last_aggregate = aggregate
                return last_aggregate
        except Exception as e:
            logger.exception(f"Error fetching recent aggregate for {symbol}: {e}")

        return current  # Fall back to cached value even if it's old

    @logfire.instrument("polygon.get_previous_close {symbol.ticker}")
    async def get_previous_close(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None:
        """Fetch the previous trading day's OHLCV aggregate for a symbol.

        Checks the aggregate cache first; only calls Polygon if not found.

        Returns:
            Aggregate with timespan of one trading session, or None on error.
        """
        import traceback
        logfire_set_attribute("stack", "".join(traceback.format_stack()))
        now = datetime.now(ZoneInfo("UTC"))
        prev_close_dt = MarketInfo.get_previous_market_close(symbol, now)
        cached = self._aggregate_cache.get_close(symbol, prev_close_dt)
        if cached is not None:
            logger.debug("Fetching previous close aggregate for %s from cache", symbol)
            logfire_set_attribute("source", "cache")
            return cached

        logfire_set_attribute("source", "api")
        try:
            logger.debug("Fetching previous close for %s on %s from API", symbol, prev_close_dt.date())
            with logfire.span("polygon.api.daily_open_close {symbol.ticker}", symbol=symbol):
                result = self._polygon_client.get_daily_open_close_agg(
                    ticker=symbol.lookup_symbol,
                    date=prev_close_dt.date(),
                )
        except RequestError:
            logger.warning("Error fetching previous close for %s, will retry next tick", symbol)
            return None
        except Exception:
            logger.exception("Error fetching previous close for %s", symbol)
            return None

        if not isinstance(result, DailyOpenCloseAgg):
            logger.warning("Unexpected previous close response type for %s: %s", symbol, type(result))
            return None
        if result.status != "OK":
            logger.warning("Previous close status not OK for %s: %s", symbol, result.status)
            return None
        if None in (result.open, result.high, result.low, result.close, result.volume):
            logger.warning("Incomplete previous close data for %s: %s", symbol, result)
            return None

        date_open = eastern_midnight(result.from_)
        aggregate = Aggregate(
            symbol,
            date_open,
            result.open,
            result.high,
            result.low,
            result.close,
            result.volume,
            MarketInfo.get_market_day_timespan(symbol),
        )
        if cache_write:
            logger.debug("Caching previous close aggregate for %s: %s", symbol, aggregate)
        return aggregate

    @logfire.instrument("polygon.get_open_close {symbol.ticker}")
    async def get_open_close(
        self, symbol: AssetSymbol, date: datetime | None = None
    ) -> DailyOpenCloseAggregate | None:
        """Fetch the daily open/close aggregate for a symbol on the given date.

        Args:
            symbol: Asset symbol
            date: The trading date to query; defaults to today (UTC).

        Returns:
            DailyOpenCloseAggregate or None on error / no data.
        """
        target = (date or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo("America/New_York")).date()
        try:
            logger.debug("Fetching open/close for %s on %s from API", symbol, target)
            with logfire.span("polygon.api.daily_open_close {symbol.ticker}", symbol=symbol):
                result = self._polygon_client.get_daily_open_close_agg(
                    ticker=symbol.lookup_symbol,
                    date=target,
                )
        except RequestError:
            logger.warning("Rate limit fetching open/close for %s", symbol)
            return None
        except Exception:
            logger.exception("Error fetching open/close for %s", symbol)
            return None

        if not isinstance(result, DailyOpenCloseAgg):
            logger.warning("Unexpected open/close response type for %s: %s", symbol, type(result))
            return None
        if result.status != "OK":
            logger.warning("Open/close status not OK for %s: %s", symbol, result.status)
            return None
        if None in (result.open, result.high, result.low, result.volume):
            logger.warning("Incomplete open/close data for %s: %s", symbol, result)
            return None

        date_open = eastern_midnight(result.from_)
        return DailyOpenCloseAggregate(
            symbol=symbol,
            date_open=date_open,
            open=result.open,
            high=result.high,
            low=result.low,
            close=result.close,
            volume=result.volume,
            pre_market=result.pre_market,
            after_hours=result.after_hours,
        )

    @logfire.instrument("polygon.get_range {symbol.ticker}")
    async def get_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        cache_write: bool = False,
        cache_read: bool = True,
        span: AggregateTimespan | None = None,
    ) -> list[Aggregate]:
        """
        Get a range of aggregates for a ticker

        Args:
            symbol: Asset symbol to fetch data for
            from_: Start datetime (inclusive, timezone aware)
            to: End datetime (inclusive, timezone aware)
            span: Candle size; defaults to 1-minute. Non-default spans bypass
                  the cache entirely (neither read nor write).

        Returns:
            List of Aggregate objects sorted by time
        """
        # Ensure datetimes are timezone aware
        if from_.tzinfo is None or to.tzinfo is None:
            raise ValueError("Datetimes must be timezone-aware")

        # Convert to UTC for consistency
        from_utc = from_.astimezone(ZoneInfo("UTC"))
        to_utc = to.astimezone(ZoneInfo("UTC"))

        effective_span = span or AggregateTimespan.default()

        # Non-minute aggregates are not cached — skip all cache logic
        if not effective_span.is_cacheable():
            return await self._fetch_range(symbol, from_utc, to_utc, span=effective_span)

        if cache_read:
            # Get cached data in this range
            cached_aggregates: list[Aggregate] = self._aggregate_cache.get_range(
                symbol, from_utc, to_utc
            )
            logger.debug("Fetched %d cached aggregates for %s from %s to %s", len(cached_aggregates), symbol, from_utc, to_utc)
        else:
            cached_aggregates = []

        # Check if we have contiguous 1-minute data
        missing_ranges: list[DateRange] = self._find_missing_ranges(
            symbol, cached_aggregates, from_utc, to_utc
        )
        logfire_set_attribute("missing_range_count", len(missing_ranges))

        # If we have all the data we need, return it
        if not missing_ranges:
            return sorted(cached_aggregates, key=lambda x: x.date_open)
        else:
            logger.debug("Identified %d missing ranges for %s from %s to %s", len(missing_ranges), symbol, from_utc, to_utc)
            for start, end in missing_ranges:
                logger.trace("Missing range for %s %s to %s", symbol, start, end)

        if len(missing_ranges) > 6:
            logger.warning("Large number of missing ranges (%d) for %s from %s to %s - Performing full fetch", len(missing_ranges), symbol, from_utc, to_utc)
            fetched = await self._fetch_range(symbol, from_utc, to_utc, cache_write=cache_write, span=effective_span)
            return sorted(fetched, key=lambda x: x.date_open)

        # Otherwise fetch the missing ranges
        all_aggregates = list(cached_aggregates)  # Start with what we have

        for start, end in missing_ranges:
            fetched = await self._fetch_range(
                symbol, start, end, cache_write=cache_write, span=effective_span
            )
            all_aggregates.extend(fetched)

        # Sort by date and return
        return sorted(all_aggregates, key=lambda x: x.date_open)

    def _find_missing_ranges(
        self, symbol: AssetSymbol, aggregates: list[Aggregate], from_: datetime, to: datetime
    ) -> list[DateRange]:
        """
        Find missing 1-minute ranges in the data.

        Args:
            aggregates: List of existing aggregates
            from_: Start time of desired range (inclusive)
            to: End time of desired range (inclusive)

        Returns:
            List of (start, end) datetime tuples representing missing ranges
            where start and end are both inclusive.
        """
        if not aggregates:
            return [(from_, to)]

        # Build set of expected minute-aligned timestamps in [from_, to]
        expected_timestamps: set[datetime] = set()

        # Advance from_ to next full minute if it has sub-minute components
        start_time = from_.replace(second = 0, microsecond=0)
        if start_time < from_:
            start_time += timedelta(minutes=1)

        current = start_time
        while current <= to:
            if not MarketInfo.is_market_closed(symbol, current):
                expected_timestamps.add(current)
            current += timedelta(minutes=1)

        # Find missing timestamps
        existing_timestamps: set[datetime] = {agg.date_open for agg in aggregates}
        missing_timestamps: list[datetime] = sorted(
            expected_timestamps - existing_timestamps
        )

        if not missing_timestamps:
            return []

        # Group consecutive missing timestamps into [start, end] ranges
        ranges: list[DateRange] = []
        range_start: datetime = missing_timestamps[0]
        prev_ts: datetime = missing_timestamps[0]

        for ts in missing_timestamps[1:]:
            if (ts - prev_ts).total_seconds() > 60:
                ranges.append((range_start, prev_ts))
                range_start = ts
            prev_ts = ts

        ranges.append((range_start, prev_ts))

        return ranges

    @logfire.instrument("polygon._fetch_range {symbol.ticker}")
    async def _fetch_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        cache_write: bool = False,
        span: AggregateTimespan | None = None,
    ) -> list[Aggregate]:
        """
        Fetch a range of aggregates from the API.

        Args:
            symbol: Asset symbol
            from_: Start datetime (inclusive)
            to: End datetime (inclusive)
            span: Candle size (defaults to 1-minute)

        Returns:
            List of fetched aggregates
        """
        effective_span = span or AggregateTimespan.default()
        result = []

        try:

            aggs: list[Agg] | HTTPResponse | None = None
            # Fetch data from API with retry
            for attempt in range(self._max_retries):
                try:
                    logger.debug("Fetching range for %s from API (attempt %d): %s to %s (span: %s)", symbol, attempt + 1, from_, to, effective_span)
                    with logfire.span("polygon.api.get_aggs {symbol.ticker}", symbol=symbol):
                        aggs = self._polygon_client.get_aggs(
                            ticker=symbol.lookup_symbol,
                            multiplier=effective_span.multiplier,
                            timespan=str(effective_span.timespan),
                            from_=from_,
                            to=to,
                        )
                    break
                except RequestError:
                    if attempt < self._max_retries - 1:
                        logger.warning(
                            f"Rate limit hit for {symbol}, waiting {self._rate_limit_sleep} seconds"
                        )
                        await asyncio.sleep(self._rate_limit_sleep)
                    else:
                        raise

            if isinstance(aggs, list):
                for agg in aggs:
                    if (
                        agg.timestamp is not None
                        and agg.open is not None
                        and agg.high is not None
                        and agg.low is not None
                        and agg.close is not None
                        and agg.volume is not None
                    ):
                        timestamp = _polygon_timestamp_to_datetime(agg.timestamp)
                        aggregate = Aggregate(
                            symbol,
                            timestamp,
                            agg.open,
                            agg.high,
                            agg.low,
                            agg.close,
                            agg.volume,
                            timedelta(minutes=1),
                        )
                        if cache_write:
                            await self._aggregate_cache.add(aggregate)
                        result.append(aggregate)

        except Exception as e:
            logger.exception(
                f"Error fetching range for {symbol} ({from_} to {to}): {e}"
            )

        logfire_set_attribute("result_count", len(result))
        return result


def _polygon_timestamp_to_datetime(timestamp: int | float) -> datetime:
    return datetime.fromtimestamp(timestamp / 1000, ZoneInfo("UTC"))
