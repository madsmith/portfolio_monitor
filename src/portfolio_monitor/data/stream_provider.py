from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol, runtime_checkable

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.service.types import AssetSymbol

type AggregateCallback = Callable[[AssetSymbol, Aggregate], Awaitable[None]]


@runtime_checkable
class StreamProvider(Protocol):
    """A data provider that pushes aggregate bars via a persistent connection.

    Implementations wrap WebSocket or streaming APIs (e.g. Alpaca live stream).
    MarketData calls connect() once at startup, then add_symbol / remove_symbol
    as the tracked symbol set changes at runtime.
    """

    async def connect(
        self,
        symbols: Iterable[AssetSymbol],
        on_aggregate: AggregateCallback,
    ) -> None:
        """Open the streaming connection and subscribe to the given symbols.

        on_aggregate is called for every incoming bar; implementations must
        not block inside on_aggregate — it is awaited on the event loop.
        """
        ...

    async def add_symbol(self, symbol: AssetSymbol) -> None:
        """Subscribe to a new symbol on the live connection."""
        ...

    async def remove_symbol(self, symbol: AssetSymbol) -> None:
        """Unsubscribe from a symbol.  No-op if the provider does not support it."""
        ...

    async def disconnect(self) -> None:
        """Close the streaming connection."""
        ...
