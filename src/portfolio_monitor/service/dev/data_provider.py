import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.data.aggregate_cache import Aggregate, AggregateCache
from portfolio_monitor.data.provider import DataProvider
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
    ) -> None:
        self._cache: AggregateCache = aggregate_cache
        self._generator: PriceGenerator = price_generator
        self._symbol_lookup: dict[str, AssetSymbol] = {s.ticker: s for s in symbols}

    async def get_aggregate(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None:
        """Generate a fresh synthetic tick and return it as an Aggregate."""
        now = datetime.now(ZoneInfo("UTC"))
        open_, high, low, close, volume = self._generator.tick(symbol.ticker)
        agg = Aggregate(
            symbol=symbol,
            date_open=now,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
            timespan=timedelta(seconds=self._generator.tick_interval),
        )
        if cache_write:
            await self._cache.add(agg)
        return agg

    async def get_previous_close(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None:
        """Return the most recent cached aggregate for the symbol."""
        return self._cache.get_current(symbol)

    async def get_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        cache_write: bool = False,
    ) -> list[Aggregate]:
        """Return cached aggregates within the given time range."""
        return self._cache.get_range(symbol, from_, to)
