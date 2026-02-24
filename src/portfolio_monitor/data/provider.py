import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from polygon import RESTClient as PolygonRESTClient
from polygon.rest.aggs import Agg
from sortedcontainers import SortedDict
from urllib3 import HTTPResponse
from urllib3.exceptions import RequestError

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.data.aggregate_cache import (
    Aggregate,
    AggregateCache,
    ms_from_datetime,
)
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)


class DataProvider:
    """Provider for fetching aggregate data with cache-first approach"""

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
        self._delay = base_delay + timedelta(minutes=1)  # Add 1 minute margin
        self._polygon_client: PolygonRESTClient = PolygonRESTClient(
            config.polygon_api_key
        )
        self._rate_limit_sleep = 12.1  # Sleep time when rate limited (slightly over 12 seconds per Polygon docs)
        self._max_retries = 5

    async def get_aggregate(self, symbol: AssetSymbol) -> Aggregate | None:
        """
        Get the most recent aggregate for a ticker

        Args:
            ticker: Ticker symbol to fetch data for

        Returns:
            Most recent Aggregate or None if not available
        """
        # Try to get from cache first
        current = self._aggregate_cache.get_current(symbol)
        now = datetime.now(ZoneInfo("UTC"))

        # Check if we have recent data in cache
        if current and (now - current.date) < self._delay:
            return current

        # Otherwise fetch from API
        try:
            # Get the most recent 1-minute bar
            to_time = now
            from_time = now - timedelta(minutes=1)

            aggs = None
            for attempt in range(self._max_retries):
                try:
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
                        )
                        await self._aggregate_cache.add(aggregate)
                        last_aggregate = aggregate
                return last_aggregate
        except Exception as e:
            logger.exception(f"Error fetching recent aggregate for {symbol}: {e}")

        return current  # Fall back to cached value even if it's old

    async def get_range(
        self, symbol: AssetSymbol, from_: datetime, to: datetime
    ) -> list[Aggregate]:
        """
        Get a range of aggregates for a ticker

        Args:
            symbol: Asset symbol to fetch data for
            from_: Start datetime (inclusive, timezone aware)
            to: End datetime (inclusive, timezone aware)

        Returns:
            List of Aggregate objects sorted by time
        """
        # Ensure datetimes are timezone aware
        if from_.tzinfo is None or to.tzinfo is None:
            raise ValueError("Datetimes must be timezone-aware")

        # Convert to UTC for consistency
        from_utc = from_.astimezone(ZoneInfo("UTC"))
        to_utc = to.astimezone(ZoneInfo("UTC"))

        # Get cached data in this range
        cached_aggregates = await self._get_cached_range(symbol, from_utc, to_utc)

        # Check if we have contiguous 1-minute data
        missing_ranges = self._find_missing_ranges(cached_aggregates, from_utc, to_utc)

        # If we have all the data we need, return it
        if not missing_ranges:
            return sorted(cached_aggregates, key=lambda x: x.date)

        # Otherwise fetch the missing ranges
        all_aggregates = list(cached_aggregates)  # Start with what we have

        for start, end in missing_ranges:
            fetched = await self._fetch_range(symbol, start, end)
            all_aggregates.extend(fetched)

        # Sort by date and return
        return sorted(all_aggregates, key=lambda x: x.date)

    async def _get_cached_range(
        self, symbol: AssetSymbol, from_: datetime, to: datetime
    ) -> list[Aggregate]:
        """
        Get cached aggregates in the given range

        This is a placeholder - you'll need to implement based on your AggregateCache API
        """
        # Convert datetimes to ms for comparison
        from_ms = ms_from_datetime(from_)
        to_ms = ms_from_datetime(to)

        # Get aggregates from cache
        result = []

        # Check if ticker exists in cache
        # TODO: Replace with an API in AggregateCache
        if symbol.ticker in self._aggregate_cache._memory_cache:
            # Get all aggregates in range
            ticker_cache = self._aggregate_cache._memory_cache[symbol.ticker]
            for timestamp_ms, agg in ticker_cache.items():
                if from_ms <= timestamp_ms <= to_ms:
                    result.append(agg)

        return result

    def _find_missing_ranges(
        self, aggregates: list[Aggregate], from_: datetime, to: datetime
    ) -> list[tuple[datetime, datetime]]:
        """
        Find missing 1-minute ranges in the data

        Args:
            aggregates: List of existing aggregates
            from_: Start time of desired range
            to: End time of desired range

        Returns:
            List of (start, end) datetime tuples representing missing ranges
        """
        if not aggregates:
            # If we have no data, the entire range is missing
            return [(from_, to)]

        # Create a sorted dictionary of existing timestamps
        sorted_aggs = SortedDict({agg.date: agg for agg in aggregates})

        # Ensure we have complete minute coverage
        expected_timestamps: set[datetime] = set()

        # Advance from_ to next full minute if it has microseconds
        start_time = from_
        if start_time.microsecond > 0 or start_time.second > 0:
            # Round up to the next minute
            start_time = (start_time + timedelta(minutes=1)).replace(
                second=0, microsecond=0
            )

        current = start_time
        while current <= to:
            expected_timestamps.add(current)
            current += timedelta(minutes=1)

        # Find missing ranges
        existing_timestamps: set[datetime] = set(sorted_aggs.keys())
        missing_timestamps: list[datetime] = sorted(
            expected_timestamps - existing_timestamps
        )

        if not missing_timestamps:
            return []

        # Group consecutive missing timestamps into ranges
        ranges: list[tuple[datetime, datetime]] = []
        range_start: datetime | None = None
        prev_ts: datetime | None = None

        for ts in missing_timestamps:
            if range_start is None:
                range_start = ts
            elif (
                prev_ts and (ts - prev_ts).total_seconds() > 60
            ):  # More than 1 minute gap
                ranges.append((range_start, prev_ts))
                range_start = ts

            prev_ts = ts

        if range_start is not None and prev_ts is not None:
            ranges.append((range_start, prev_ts))

        return ranges

    async def _fetch_range(
        self, symbol: AssetSymbol, from_: datetime, to: datetime
    ) -> list[Aggregate]:
        """
        Fetch a range of aggregates from the API

        Args:
            symbol: Asset symbol
            from_: Start datetime
            to: End datetime

        Returns:
            List of fetched aggregates
        """
        result = []

        try:
            # Calculate how many minutes we need to fetch
            minutes_delta = (
                int((to - from_).total_seconds() / 60) + 1
            )  # +1 to include both endpoints
            limit = min(50000, minutes_delta)  # Polygon API limit

            aggs: list[Agg] | HTTPResponse | None = None
            # Fetch data from API with retry
            for attempt in range(self._max_retries):
                try:
                    aggs = self._polygon_client.get_aggs(
                        ticker=symbol.lookup_symbol,
                        multiplier=1,
                        timespan="minute",
                        from_=from_,
                        to=to,
                        limit=limit,
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
                        )
                        await self._aggregate_cache.add(aggregate)
                        result.append(aggregate)

        except Exception as e:
            logger.exception(
                f"Error fetching range for {symbol} ({from_} to {to}): {e}"
            )

        return result


def _polygon_timestamp_to_datetime(timestamp: int | float) -> datetime:
    return datetime.fromtimestamp(timestamp / 1000, ZoneInfo("UTC"))
