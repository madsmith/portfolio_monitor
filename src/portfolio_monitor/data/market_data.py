"""MarketData — central market data hub.

Owns the in-memory (last-known) and SQLite (historical) aggregate caches.
Accepts pull providers (REST) and stream providers (WebSocket/push).
Publishes AggregateUpdated on the EventBus and dispatches per-symbol
subscriber callbacks when new aggregates arrive.

Pull providers are tried in order; the first non-None result wins (primary +
fallback semantics).  Stream providers are connected at start() and push bars
via on_aggregate callbacks.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import uuid
from zoneinfo import ZoneInfo

import logfire

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import (
    Aggregate,
    AggregateCache,
    DailyOpenCloseAggregate,
)
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.data.rest_provider import RESTProvider
from portfolio_monitor.data.stream_provider import StreamProvider
from portfolio_monitor.data.timespan import AggregateTimespan
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)

type AggregateCallback = Callable[[Aggregate], Awaitable[None] | None]


@dataclass
class SubscriptionHandle:
    symbol: AssetSymbol
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class MarketData:
    """Central market data hub.

    Usage
    -----
    market_data = MarketData(bus, cache, pull_providers=[massive], stream_providers=[alpaca])
    await market_data.start()

    # Immediate best-known price (may be slightly stale):
    agg = await market_data.get_aggregate(symbol)

    # Subscribe to live updates for a symbol:
    handle = market_data.subscribe(symbol, my_callback)

    # Later:
    market_data.unsubscribe(handle)
    await market_data.stop()
    """

    def __init__(
        self,
        bus: EventBus,
        aggregate_cache: AggregateCache,
        config: PortfolioMonitorConfig,
        rest_providers: list[RESTProvider] | None = None,
        stream_providers: list[StreamProvider] | None = None,
    ) -> None:
        self._bus: EventBus = bus
        self._cache: AggregateCache = aggregate_cache
        self._max_current_age: timedelta = timedelta(seconds=config.market_data_max_current_age)
        self._max_contiguous_gap: timedelta = timedelta(seconds=config.market_data_max_contiguous_gap)
        self._poll_interval: timedelta = timedelta(seconds=config.market_data_poll_interval)
        self._rest_providers: list[RESTProvider] = rest_providers or []
        self._stream_providers: list[StreamProvider] = stream_providers or []

        # In-memory last-known aggregate per symbol (survives between polls)
        self._latest: dict[AssetSymbol, Aggregate] = {}

        # Symbols being tracked
        self._symbols: set[AssetSymbol] = set()
        # Symbols currently covered by a stream provider (skip from poll loop)
        self._streamed_symbols: set[AssetSymbol] = set()
        # Last poll time per symbol for the pull loop
        self._last_polled: dict[AssetSymbol, datetime] = {}

        # Per-symbol subscriber callbacks: symbol → {handle_id: callback}
        self._subscribers: dict[AssetSymbol, dict[str, AggregateCallback]] = {}

        self._running: bool = False
        self._poll_task: asyncio.Task | None = None

    # ── Symbol lifecycle ──────────────────────────────────────────────────────

    def register_symbol(self, symbol: AssetSymbol) -> None:
        """Begin tracking a symbol.

        Pull providers will include it in the next poll cycle.
        Stream providers are subscribed immediately if already connected.
        """
        if symbol in self._symbols:
            return
        self._symbols.add(symbol)
        logger.debug("MarketData: registered symbol %s", symbol)
        if self._running:
            for provider in self._stream_providers:
                asyncio.create_task(provider.add_symbol(symbol))

    def unregister_symbol(self, symbol: AssetSymbol) -> None:
        """Stop tracking a symbol.

        Stream providers are asked to unsubscribe (no-op if unsupported).
        In-memory latest bar is cleared; SQLite history is preserved.
        """
        if symbol not in self._symbols:
            return
        self._symbols.discard(symbol)
        self._latest.pop(symbol, None)
        self._streamed_symbols.discard(symbol)
        self._last_polled.pop(symbol, None)
        logger.debug("MarketData: unregistered symbol %s", symbol)
        if self._running:
            for provider in self._stream_providers:
                asyncio.create_task(provider.remove_symbol(symbol))

    # ── Immediate / best-known data ───────────────────────────────────────────

    @logfire.instrument("market_data.get_aggregate {symbol.ticker}")
    async def get_aggregate(self, symbol: AssetSymbol) -> Aggregate | None:
        """Return the best known aggregate for a symbol.

        Resolution order:
          1. In-memory latest bar, if within max_current_age.
          2. SQLite cache (most recent stored bar for the symbol).
          3. Pull providers in order — first non-None result wins.
          4. Cold-start: fetch previous session's 1-min bars and return the last.

        Stream providers are expected to keep the in-memory cache warm via
        _on_aggregate callbacks, so for streaming setups the provider fetch
        (step 3) should rarely be needed.
        """
        latest = self._latest.get(symbol)
        if latest is not None:
            age = datetime.now(latest.date_open.tzinfo) - latest.date_open
            if age < self._max_current_age:
                return latest

        # In-memory miss or stale — check the SQLite cache next
        cached = await self._cache.get_current(symbol)
        if cached is not None:
            age = datetime.now(cached.date_open.tzinfo) - cached.date_open
            if age < self._max_current_age:
                self._latest[symbol] = cached
                return cached

        # Cache miss or stale — try pull providers in order
        for provider in self._rest_providers:
            try:
                agg = await provider.get_aggregate(symbol)
                if agg is not None:
                    await self._on_aggregate(symbol, agg)
                    return agg
            except Exception:
                logger.warning("MarketData: pull provider %s failed for %s", type(provider).__name__, symbol, exc_info=True)

        # Cold-start: no current bar available — fetch the most recent bar from
        # the previous session (includes post-close bars if present).
        cold = await self._cold_start_aggregate(symbol)
        if cold is not None:
            await self._on_aggregate(symbol, cold)
            return cold

        return latest or cached  # return stale rather than None if all else fails

    @logfire.instrument("market_data.get_range {symbol.ticker}")
    async def get_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        span: AggregateTimespan | None = None,
    ) -> list[Aggregate]:
        """Return bars for a time range.

        Reads from the cache first.  Missing bars are fetched from pull
        providers in order (first non-empty result wins) and written back
        to the cache.  Stream providers do not serve historical queries.
        """
        cached = self._cache.get_range(symbol, from_, to)
        if self._is_contiguous_range(symbol, cached, from_, to):
            return cached

        for provider in self._rest_providers:
            try:
                bars = await provider.get_range(symbol, from_, to, span=span)
                if bars:
                    for bar in bars:
                        await self._cache.add(bar)
                    return bars
            except Exception:
                logger.warning("MarketData: get_range failed on %s", type(provider).__name__, exc_info=True)
        return []

    @logfire.instrument("market_data.get_previous_close {symbol.ticker}")
    async def get_previous_close(self, symbol: AssetSymbol) -> Aggregate | None:
        """Return the previous session's closing aggregate (cache-first).

        Resolves the previous close datetime via MarketInfo, checks the cache,
        then falls through to pull providers on a miss.  The provider result is
        written to the cache so subsequent calls are served locally.
        """
        now = datetime.now(ZoneInfo("UTC"))
        prev_close_dt = MarketInfo.get_previous_market_close(symbol, now)

        cached = await self._cache.get_close(symbol, prev_close_dt)
        if cached is not None:
            return cached

        for provider in self._rest_providers:
            try:
                result = await provider.get_previous_close(symbol)
                if result is not None:
                    await self._cache.add(result)
                    return result
            except Exception:
                logger.warning("MarketData: get_previous_close failed on %s", type(provider).__name__, exc_info=True)
        return None

    @logfire.instrument("market_data.get_open_close {symbol.ticker}")
    async def get_open_close(
        self, symbol: AssetSymbol, date: datetime | None = None
    ) -> DailyOpenCloseAggregate | None:
        """Return the daily open/close aggregate for a given date.

        Checks the cache (memory then SQLite) first.  Falls through to pull
        providers in order and writes the result back to the cache.
        """
        cached = await self._cache.get_open_close(symbol, date)
        if cached is not None:
            return cached

        for provider in self._rest_providers:
            try:
                result = await provider.get_open_close(symbol, date)
                if result is not None:
                    await self._cache.add_open_close(result)
                    return result
            except Exception:
                logger.warning("MarketData: get_open_close failed on %s", type(provider).__name__, exc_info=True)
        return None

    @logfire.instrument("market_data.get_daily_range {symbol.ticker}")
    async def get_daily_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
    ) -> list[DailyOpenCloseAggregate]:
        """Return a range of daily OHLCV aggregates.

        Checks the cache (memory then SQLite) first.  Falls through to pull
        providers in order and writes fetched bars back to the cache.
        """
        cached = await self._cache.get_open_close_range(symbol, from_, to)
        if cached:
            return cached

        for provider in self._rest_providers:
            try:
                bars = await provider.get_daily_range(symbol, from_, to)
                if bars:
                    for bar in bars:
                        await self._cache.add_open_close(bar)
                    return bars
            except Exception:
                logger.warning("MarketData: get_daily_range failed on %s", type(provider).__name__, exc_info=True)
        return []

    # ── Subscriptions ─────────────────────────────────────────────────────────

    def subscribe(
        self,
        symbol: AssetSymbol,
        callback: AggregateCallback,
    ) -> SubscriptionHandle:
        """Register a callback to be called when a new aggregate arrives for symbol.

        The callback receives the Aggregate and may be sync or async.
        Returns a handle that can be passed to unsubscribe().
        """
        handle = SubscriptionHandle(symbol=symbol)
        self._subscribers.setdefault(symbol, {})[handle.id] = callback
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """Remove a previously registered subscription."""
        symbol_subs = self._subscribers.get(handle.symbol)
        if symbol_subs:
            symbol_subs.pop(handle.id, None)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Connect stream providers and start the pull poll loop."""
        if self._running:
            logger.warning("MarketData already running")
            return
        self._running = True

        for provider in self._stream_providers:
            try:
                await provider.connect(list(self._symbols), self._on_stream_aggregate)
                self._streamed_symbols.update(self._symbols)
                logger.info("MarketData: connected stream provider %s", type(provider).__name__)
            except Exception:
                logger.exception("MarketData: failed to connect stream provider %s", type(provider).__name__)

        if self._rest_providers and not self._stream_providers:
            self._poll_task = asyncio.create_task(self._poll_loop())

        logger.info(
            "MarketData: started (%d pull, %d stream providers, %d symbols)",
            len(self._rest_providers), len(self._stream_providers), len(self._symbols),
        )

    async def stop(self) -> None:
        """Disconnect stream providers and stop the pull poll loop."""
        if not self._running:
            return
        self._running = False

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        for provider in self._stream_providers:
            try:
                await provider.disconnect()
            except Exception:
                logger.exception("MarketData: error disconnecting stream provider %s", type(provider).__name__)

        logger.info("MarketData: stopped")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _cold_start_aggregate(self, symbol: AssetSymbol) -> Aggregate | None:
        """Fetch the last known 1-min aggregate, including any post-close data.

        Fetches from the previous session's market open through now on the
        first attempt (capturing regular + post-close aggs). On subsequent
        attempts steps the window back one session at a time, up to 3 tries,
        to skip market holidays.
        """
        now = datetime.now(ZoneInfo("UTC"))
        session_timespan = MarketInfo.get_market_day_timespan(symbol)
        candidate_close = MarketInfo.get_previous_market_close(symbol, now)
        window_end = now

        for _ in range(3):
            window_start = candidate_close - session_timespan
            aggs = await self.get_range(symbol, window_start, window_end)
            if aggs:
                logger.debug("MarketData: cold-start for %s — last agg from %s", symbol, aggs[-1].date_open)
                return aggs[-1]
            # No aggs — likely a holiday, step window back one more session
            window_end = window_start
            candidate_close = MarketInfo.get_previous_market_close(symbol, candidate_close)

        return None

    async def _poll_loop(self) -> None:
        """Background task: polls pull providers for symbols not covered by a stream."""
        try:
            while self._running:
                now = datetime.now(ZoneInfo("UTC"))
                due = [
                    s for s in self._symbols
                    if s not in self._streamed_symbols
                    and MarketInfo.is_market_open(s, now)
                    and (
                        s not in self._last_polled
                        or now - self._last_polled[s] >= self._poll_interval
                    )
                ]

                if due:
                    with logfire.span(
                        "market_data.poll_tick",
                        symbol_count=len(self._symbols),
                        symbols_polled=len(due),
                    ):
                        results = await asyncio.gather(
                            *[self._poll_symbol(s) for s in due],
                            return_exceptions=True,
                        )
                    for symbol, result in zip(due, results):
                        if isinstance(result, Exception):
                            logger.warning("MarketData: poll error for %s: %s", symbol, result)
                        else:
                            self._last_polled[symbol] = now

                await asyncio.sleep(self._poll_interval.total_seconds())
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("MarketData: poll loop crashed")

    @logfire.instrument("market_data.poll_symbol {symbol.ticker}")
    async def _poll_symbol(self, symbol: AssetSymbol) -> None:
        """Fetch the latest aggregate for a single symbol via pull providers."""
        for provider in self._rest_providers:
            try:
                agg = await provider.get_aggregate(symbol)
                if agg is not None:
                    await self._on_aggregate(symbol, agg)
                    return
            except Exception:
                logger.warning("MarketData: pull failed for %s on %s", symbol, type(provider).__name__, exc_info=True)

    # ── Event Handlers ────────────────────────────────────────────────────────

    async def _on_stream_aggregate(self, symbol: AssetSymbol, agg: Aggregate) -> None:
        """Callback for stream provider bars — marks symbol as streamed, then processes."""
        self._streamed_symbols.add(symbol)
        await self._on_aggregate(symbol, agg)

    async def _on_aggregate(self, symbol: AssetSymbol, agg: Aggregate) -> None:
        """Handle a new aggregate from any source (poll or stream).

        Updates the in-memory latest bar, writes to cache, publishes
        AggregateUpdated on the bus, and dispatches per-symbol callbacks.
        """
        self._latest[symbol] = agg
        await self._cache.add(agg)

        await self._bus.publish(AggregateUpdated(symbol=symbol, aggregate=agg))

        symbol_subs = self._subscribers.get(symbol)
        if symbol_subs:
            for callback in list(symbol_subs.values()):
                try:
                    result = callback(agg)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("MarketData: error in subscriber callback for %s", symbol)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_contiguous_range(
        self, symbol: AssetSymbol, bars: list[Aggregate], from_: datetime, to: datetime
    ) -> bool:
        """Return True if bars form a sufficiently complete coverage of [from_, to].

        A range is considered contiguous when:
          - There is at least one bar.
          - The first bar is within max_contiguous_gap of from_.
          - The last bar is within max_contiguous_gap of to (or the market has
            since closed, meaning no more bars are expected).
          - No consecutive pair of bars has a gap larger than max_contiguous_gap.

        Skips the trailing-edge check when the market is currently closed for
        the symbol, since the last bar naturally sits at the session close
        rather than near `to`.
        """
        if not bars:
            return False

        gap = self._max_contiguous_gap
        now = datetime.now(from_.tzinfo)

        if bars[0].date_open - from_ > gap:
            return False

        market_open = MarketInfo.is_market_open(symbol, now)
        if market_open and to - bars[-1].date_open > gap:
            return False

        for a, b in zip(bars, bars[1:]):
            if b.date_open - a.date_open > gap:
                return False

        return True