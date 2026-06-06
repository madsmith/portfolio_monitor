import logging
from datetime import datetime

from portfolio_monitor.data import AggregateCache, AggregateTimespan, DailyOpenCloseAggregate
from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.service.types import AssetSymbol

from .price_generator import PriceGenerator

logger = logging.getLogger(__name__)


class DevDataProvider:
    """Synthetic data provider for dev mode.

    Serves prices from the in-memory cache (populated by the synthetic source)
    instead of calling real market APIs.
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

    def register_symbol(self, symbol: AssetSymbol) -> None:
        self._symbol_lookup[symbol.ticker] = symbol

    def unregister_symbol(self, symbol: AssetSymbol) -> None:
        self._symbol_lookup.pop(symbol.ticker, None)

    async def get_aggregate(self, symbol: AssetSymbol) -> Aggregate | None:
        return await self._cache.get_current(symbol)

    async def get_previous_close(self, symbol: AssetSymbol) -> Aggregate | None:
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
        span: AggregateTimespan | None = None,
    ) -> list[Aggregate]:
        effective_span = span or AggregateTimespan.default()
        if not effective_span.is_cacheable():
            return []
        return self._cache.get_range(symbol, from_, to)

    async def get_open_close(
        self, symbol: AssetSymbol, date: datetime | None = None
    ) -> DailyOpenCloseAggregate | None:
        return None

    async def get_daily_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
    ) -> list[DailyOpenCloseAggregate]:
        return []
