from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from portfolio_monitor.data.aggregate_cache import Aggregate, DailyOpenCloseAggregate
from portfolio_monitor.data.timespan import AggregateTimespan
from portfolio_monitor.service.types import AssetSymbol


@runtime_checkable
class RESTProvider(Protocol):
    """A data provider that serves aggregate bars via synchronous REST requests.

    Implementations wrap HTTP APIs (e.g. Massive, Alpaca historical).
    MarketData calls these on demand (get_aggregate, get_range, etc.) and
    via the background poll loop when no stream providers are configured.
    Caching is handled by MarketData — implementations should not cache.
    """

    async def get_aggregate(self, symbol: AssetSymbol) -> Aggregate | None: ...

    async def get_previous_close(self, symbol: AssetSymbol) -> Aggregate | None: ...

    async def get_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        span: AggregateTimespan | None = None,
    ) -> list[Aggregate]: ...

    async def get_open_close(
        self,
        symbol: AssetSymbol,
        date: datetime | None = None,
    ) -> DailyOpenCloseAggregate | None: ...

    async def get_daily_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
    ) -> list[DailyOpenCloseAggregate]: ...
