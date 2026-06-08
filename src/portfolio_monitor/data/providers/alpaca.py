"""Alpaca Markets data provider.

Implements both RESTProvider (historical/intraday REST API) and StreamProvider
(WebSocket live 1-min bars) for US equities via alpaca-py.

Usage
-----
provider = AlpacaProvider(config)

# REST — on-demand historical data:
agg = await provider.get_aggregate(symbol)
bars = await provider.get_range(symbol, from_, to)

# Stream — live bars pushed to a callback:
await provider.connect(symbols, on_aggregate)
await provider.add_symbol(new_symbol)
await provider.disconnect()
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
import logfire

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core.datetime import eastern_midnight
from portfolio_monitor.data.aggregate_cache import Aggregate, DailyOpenCloseAggregate
from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.data.stream_provider import AggregateCallback
from portfolio_monitor.data.timespan import AggregateTimespan, Timespan
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)

_TIMESPAN_TO_ALPACA: dict[Timespan, TimeFrameUnit] = {
    Timespan.MINUTE: TimeFrameUnit.Minute,
    Timespan.HOUR:   TimeFrameUnit.Hour,
    Timespan.DAY:    TimeFrameUnit.Day,
    Timespan.WEEK:   TimeFrameUnit.Week,
    Timespan.MONTH:  TimeFrameUnit.Month,
}


class AlpacaProvider:
    """Alpaca Markets provider satisfying both RESTProvider and StreamProvider.

    REST calls are made via StockHistoricalDataClient (SIP feed).
    Streaming uses StockDataStream (WebSocket, 1-min bars).
    Only US equity symbols are supported; crypto requires a separate client.
    """

    def __init__(self, config: PortfolioMonitorConfig) -> None:
        self._api_key: str = config.alpaca_api_key
        self._secret_key: str = config.alpaca_secret_key
        self._rest_client: StockHistoricalDataClient = StockHistoricalDataClient(
            self._api_key, self._secret_key
        )
        self._stream: StockDataStream | None = None
        self._stream_task: asyncio.Task | None = None
        self._on_aggregate: AggregateCallback | None = None
        # ticker string → AssetSymbol — needed to reconstruct the typed symbol
        # from the raw string Alpaca passes back in stream bar events.
        self._symbol_map: dict[str, AssetSymbol] = {}

    # ── RESTProvider ──────────────────────────────────────────────────────────

    @logfire.instrument("alpaca.get_aggregate {symbol.ticker}")
    async def get_aggregate(self, symbol: AssetSymbol) -> Aggregate | None:
        """Return the most recent 1-min bar (looks back up to 15 minutes)."""
        if symbol.is_base_currency:
            now = datetime.now(ZoneInfo("UTC")).replace(second=0, microsecond=0)
            return Aggregate(symbol, now, 1.0, 1.0, 1.0, 1.0, 0.0, timedelta(minutes=1))

        now = datetime.now(ZoneInfo("UTC"))
        now_binned = now.replace(second=0, microsecond=0)
        bars = await asyncio.to_thread(
            self._rest_client.get_stock_bars,
            StockBarsRequest(
                symbol_or_symbols=symbol.ticker,
                timeframe=TimeFrame.Minute,
                start=now_binned - timedelta(minutes=15),
                end=now_binned,
                feed=DataFeed.SIP,
            ),
        )
        bar_list = bars.data.get(symbol.ticker, [])
        return _bar_to_aggregate(bar_list[-1], symbol) if bar_list else None

    @logfire.instrument("alpaca.get_previous_close {symbol.ticker}")
    async def get_previous_close(self, symbol: AssetSymbol) -> Aggregate | None:
        """Return the previous session's closing bar as an Aggregate.

        Steps back up to 3 extra business days to skip market holidays
        (Alpaca returns an empty list for holiday dates).
        """
        if symbol.is_base_currency:
            now = datetime.now(ZoneInfo("UTC"))
            return Aggregate(symbol, now, 1.0, 1.0, 1.0, 1.0, 0.0, timedelta(hours=24))

        now = datetime.now(ZoneInfo("UTC"))
        candidate_dt = MarketInfo.get_previous_market_close(symbol, now)

        for _ in range(3):
            day_start = candidate_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            bars = await asyncio.to_thread(
                self._rest_client.get_stock_bars,
                StockBarsRequest(
                    symbol_or_symbols=symbol.ticker,
                    timeframe=TimeFrame.Day,
                    start=day_start,
                    end=candidate_dt,
                    feed=DataFeed.SIP,
                ),
            )
            bar_list = bars.data.get(symbol.ticker, [])
            if bar_list:
                b = bar_list[-1]
                date_open = eastern_midnight(
                    b.timestamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()
                )
                return Aggregate(
                    symbol=symbol,
                    date_open=date_open,
                    open=float(b.open),
                    high=float(b.high),
                    low=float(b.low),
                    close=float(b.close),
                    volume=float(b.volume),
                    timespan=MarketInfo.get_market_day_timespan(symbol),
                )
            logger.debug("Previous close empty for %s on %s — stepping back", symbol, candidate_dt.date())
            candidate_dt = MarketInfo.get_previous_market_close(symbol, candidate_dt)

        return None

    @logfire.instrument("alpaca.get_range {symbol.ticker}")
    async def get_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        span: AggregateTimespan | None = None,
    ) -> list[Aggregate]:
        """Return 1-min (or custom span) bars for the given range."""
        if from_.tzinfo is None or to.tzinfo is None:
            raise ValueError("Datetimes must be timezone-aware")
        timeframe = _to_alpaca_timeframe(span) if span else TimeFrame.Minute
        bars = await asyncio.to_thread(
            self._rest_client.get_stock_bars,
            StockBarsRequest(
                symbol_or_symbols=symbol.ticker,
                timeframe=timeframe,
                start=from_,
                end=to,
                feed=DataFeed.SIP,
            ),
        )
        return [_bar_to_aggregate(b, symbol) for b in bars.data.get(symbol.ticker, [])]

    @logfire.instrument("alpaca.get_open_close {symbol.ticker}")
    async def get_open_close(
        self,
        symbol: AssetSymbol,
        date: datetime | None = None,
    ) -> DailyOpenCloseAggregate | None:
        """Return the daily OHLCV bar for the given date (defaults to today)."""
        if symbol.is_base_currency:
            target_dt = date or datetime.now(ZoneInfo("UTC"))
            return DailyOpenCloseAggregate(
                symbol=symbol, date_open=target_dt,
                open=1.0, high=1.0, low=1.0, close=1.0,
                volume=0.0, pre_market=None, after_hours=None,
            )

        target = date or datetime.now(ZoneInfo("UTC"))
        day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        bars = await asyncio.to_thread(
            self._rest_client.get_stock_bars,
            StockBarsRequest(
                symbol_or_symbols=symbol.ticker,
                timeframe=TimeFrame.Day,
                start=day_start,
                end=day_end,
                feed=DataFeed.SIP,
            ),
        )
        bar_list = bars.data.get(symbol.ticker, [])
        if not bar_list:
            return None
        return _bar_to_daily(bar_list[0], symbol)

    @logfire.instrument("alpaca.get_daily_range {symbol.ticker}")
    async def get_daily_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
    ) -> list[DailyOpenCloseAggregate]:
        """Return daily OHLCV bars for the given date range."""
        if symbol.is_base_currency:
            return []

        bars = await asyncio.to_thread(
            self._rest_client.get_stock_bars,
            StockBarsRequest(
                symbol_or_symbols=symbol.ticker,
                timeframe=TimeFrame.Day,
                start=from_,
                end=to,
                feed=DataFeed.SIP,
            ),
        )
        return [_bar_to_daily(b, symbol) for b in bars.data.get(symbol.ticker, [])]

    # ── StreamProvider ────────────────────────────────────────────────────────

    async def connect(
        self,
        symbols: Iterable[AssetSymbol],
        on_aggregate: AggregateCallback,
    ) -> None:
        """Open the WebSocket stream and subscribe to the given symbols."""
        self._on_aggregate = on_aggregate
        self._stream = StockDataStream(self._api_key, self._secret_key, feed=DataFeed.SIP)

        tickers: list[str] = []
        for symbol in symbols:
            self._symbol_map[symbol.ticker] = symbol
            tickers.append(symbol.ticker)

        if tickers:
            self._stream.subscribe_bars(self._handle_bar, *tickers)

        self._stream_task = asyncio.create_task(self._stream._run_forever())
        logger.info("AlpacaProvider: stream connected (%d symbols)", len(tickers))

    async def add_symbol(self, symbol: AssetSymbol) -> None:
        """Subscribe to a new symbol on the live stream."""
        self._symbol_map[symbol.ticker] = symbol
        if self._stream is not None:
            self._stream.subscribe_bars(self._handle_bar, symbol.ticker)

    async def remove_symbol(self, symbol: AssetSymbol) -> None:
        """Unsubscribe from a symbol."""
        self._symbol_map.pop(symbol.ticker, None)
        if self._stream is not None:
            self._stream.unsubscribe_bars(symbol.ticker)

    async def disconnect(self) -> None:
        """Stop the stream and clean up."""
        if self._stream is not None:
            # stop_ws() signals _run_forever to exit cleanly via the stop queue.
            # Calling stream.stop() here would deadlock — it uses
            # run_coroutine_threadsafe on the same running event loop.
            await self._stream.stop_ws()
            self._stream = None
        if self._stream_task is not None:
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        logger.info("AlpacaProvider: stream disconnected")

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _handle_bar(self, bar: Bar) -> None:
        """Receive a live bar from the WebSocket and forward to MarketData."""
        symbol = self._symbol_map.get(bar.symbol)
        if symbol is None or self._on_aggregate is None:
            return
        await self._on_aggregate(symbol, _bar_to_aggregate(bar, symbol))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar_to_aggregate(bar: Bar, symbol: AssetSymbol) -> Aggregate:
    return Aggregate(
        symbol=symbol,
        date_open=bar.timestamp,
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume),
        timespan=timedelta(minutes=1),
    )


def _bar_to_daily(bar: Bar, symbol: AssetSymbol) -> DailyOpenCloseAggregate:
    date_open = eastern_midnight(
        bar.timestamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    )
    return DailyOpenCloseAggregate(
        symbol=symbol,
        date_open=date_open,
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=float(bar.volume),
        pre_market=None,
        after_hours=None,
    )


def _to_alpaca_timeframe(span: AggregateTimespan) -> TimeFrame:
    unit = _TIMESPAN_TO_ALPACA.get(span.timespan)
    if unit is None:
        raise ValueError(f"Unsupported timespan for Alpaca: {span}")
    return TimeFrame(span.multiplier, unit)
