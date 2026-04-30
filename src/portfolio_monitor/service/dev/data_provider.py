import logging
from datetime import datetime

from portfolio_monitor.data import Aggregate, AggregateCache, AggregateTimespan, DataProvider, DailyOpenCloseAggregate
from portfolio_monitor.service.types import AssetSymbol

from .price_generator import PriceGenerator

logger = logging.getLogger(__name__)


class DevDataProvider(DataProvider):
    """DataProvider substitute that uses synthetic prices instead of Polygon.

    Mirrors the public API of DataProvider so it can be passed to
    DetectionService and any future API endpoints that query market data.
    """

    def __init__(
        self,
        aggregate_cache: AggregateCache,
        price_generator: PriceGenerator,
        symbols: list[AssetSymbol],
        seed_aggregates: dict[str, Aggregate] | None = None,
    ) -> None:
        self._cache: AggregateCache = aggregate_cache
        self._generator: PriceGenerator = price_generator
        self._symbol_lookup: dict[str, AssetSymbol] = {s.ticker: s for s in symbols}
        self._seed_aggregates: dict[str, Aggregate] = seed_aggregates or {}

    async def get_aggregate(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None:
        """Return the most recently cached aggregate for the symbol."""
        return await self._cache.get_current(symbol)

    async def get_previous_close(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None:
        """Return the seed aggregate (Polygon previous close) for the symbol."""
        seed = self._seed_aggregates.get(symbol.ticker)
        if seed is not None:
            return seed
        return await self._cache.get_current(symbol)

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
        """Return cached 1-minute aggregates within the given time range.

        Non-default spans return an empty list — DevDataProvider only holds
        minute-resolution data and does not downsample.
        """
        effective_span = span or AggregateTimespan.default()
        if not effective_span.is_cacheable():
            return []
        return self._cache.get_range(symbol, from_, to)

    async def get_open_close(
        self, symbol: AssetSymbol, date: datetime | None = None
    ) -> DailyOpenCloseAggregate | None:
        """Not supported in dev mode — returns None."""
        return None

    async def get_daily_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        cache_write: bool = False,
    ) -> list[DailyOpenCloseAggregate]:
        """Not supported in dev mode — returns empty list."""
        return []
