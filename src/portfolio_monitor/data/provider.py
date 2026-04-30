from datetime import datetime
from typing import Protocol, runtime_checkable

from portfolio_monitor.data.aggregate_cache import Aggregate, DailyOpenCloseAggregate
from portfolio_monitor.data.timespan import AggregateTimespan
from portfolio_monitor.service.types import AssetSymbol


@runtime_checkable
class DataProvider(Protocol):
    """Interface for fetching aggregate market data."""

    async def get_aggregate(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None: ...

    async def get_previous_close(
        self, symbol: AssetSymbol, *, cache_write: bool = False
    ) -> Aggregate | None: ...

    async def get_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        cache_write: bool = False,
        cache_read: bool = True,
        span: AggregateTimespan | None = None,
    ) -> list[Aggregate]: ...

    async def get_open_close(
        self, symbol: AssetSymbol, date: datetime | None = None, *, cache_write: bool = False
    ) -> DailyOpenCloseAggregate | None: ...
