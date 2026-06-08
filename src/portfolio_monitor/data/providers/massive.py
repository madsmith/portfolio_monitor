"""Massive.com REST data provider.

Implements RESTProvider using the Massive REST API.
Caching is the responsibility of MarketData — this provider fetches only.

A single attempt is made per call; on failure the exception propagates so
MarketData can fall over to the next provider immediately.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import logfire
from massive import RESTClient as MassiveRESTClient, BadResponse
from massive.rest.aggs import Agg, DailyOpenCloseAgg
from urllib3 import HTTPResponse

from portfolio_monitor.config import PortfolioMonitorConfig
from portfolio_monitor.core import eastern_midnight
from portfolio_monitor.data.aggregate_cache import Aggregate, DailyOpenCloseAggregate
from portfolio_monitor.data.market_info import MarketInfo
from portfolio_monitor.data.timespan import AggregateTimespan
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.utils import get_trace_logger

logger = get_trace_logger(__name__)


class MassiveProvider:
    """Massive.com REST provider satisfying the RESTProvider protocol.

    Wraps the blocking Massive RESTClient in asyncio.to_thread calls.
    Fails fast on error — retry and failover are MarketData's responsibility.
    """

    def __init__(self, config: PortfolioMonitorConfig) -> None:
        self._client: MassiveRESTClient = MassiveRESTClient(
            config.massive_api_key,
            connect_timeout=config.massive_request_timeout,
            read_timeout=config.massive_request_timeout,
        )
        self._client.client.connection_pool_kw["maxsize"] = config.massive_max_concurrent
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(config.massive_max_concurrent)

    # ── RESTProvider ──────────────────────────────────────────────────────────

    @logfire.instrument("massive.get_aggregate {symbol.ticker}")
    async def get_aggregate(self, symbol: AssetSymbol) -> Aggregate | None:
        """Return the most recent 1-min bar from Massive."""
        if symbol.is_base_currency:
            now = datetime.now(ZoneInfo("UTC")).replace(second=0, microsecond=0)
            return Aggregate(symbol, now, 1.0, 1.0, 1.0, 1.0, 0.0, timedelta(minutes=1))

        now = datetime.now(ZoneInfo("UTC"))
        now_binned = now.replace(second=0, microsecond=0)

        aggs = await self._fetch_aggs(
            symbol, now_binned - timedelta(minutes=1), now_binned,
            timespan="minute", limit=1,
        )
        return aggs[-1] if aggs else None

    @logfire.instrument("massive.get_previous_close {symbol.ticker}")
    async def get_previous_close(self, symbol: AssetSymbol) -> Aggregate | None:
        """Return the previous session's closing aggregate."""
        if symbol.is_base_currency:
            now = datetime.now(ZoneInfo("UTC"))
            return Aggregate(symbol, now, 1.0, 1.0, 1.0, 1.0, 0.0, timedelta(hours=24))

        now = datetime.now(ZoneInfo("UTC"))
        candidate_dt = MarketInfo.get_previous_market_close(symbol, now)

        # Step back up to 3 extra business days to skip market holidays.
        for _ in range(3):
            try:
                async with self._semaphore:
                    with logfire.span("massive.api.daily_open_close {symbol.ticker}", symbol=symbol):
                        result = await asyncio.to_thread(
                            self._client.get_daily_open_close_agg,
                            ticker=symbol.lookup_symbol,
                            date=candidate_dt.date(),
                        )
            except BadResponse as e:
                if "NOT_FOUND" in str(e):
                    logger.debug("Previous close NOT_FOUND for %s on %s — stepping back", symbol, candidate_dt.date())
                    candidate_dt = MarketInfo.get_previous_market_close(symbol, candidate_dt)
                    continue
                raise

            if not isinstance(result, DailyOpenCloseAgg) or result.status != "OK":
                return None
            if None in (result.open, result.high, result.low, result.close, result.volume):
                return None

            date_open = eastern_midnight(result.from_)
            return Aggregate(
                symbol,
                date_open,
                result.open,
                result.high,
                result.low,
                result.close,
                result.volume,
                MarketInfo.get_market_day_timespan(symbol),
            )

        return None

    @logfire.instrument("massive.get_range {symbol.ticker}")
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
        effective = span or AggregateTimespan.default()
        return await self._fetch_aggs(
            symbol, from_, to,
            timespan=str(effective.timespan),
            multiplier=effective.multiplier,
        )

    @logfire.instrument("massive.get_open_close {symbol.ticker}")
    async def get_open_close(
        self,
        symbol: AssetSymbol,
        date: datetime | None = None,
    ) -> DailyOpenCloseAggregate | None:
        """Return the daily open/close aggregate for the given date."""
        if symbol.is_base_currency:
            target_dt = date or datetime.now(ZoneInfo("UTC"))
            return DailyOpenCloseAggregate(
                symbol=symbol, date_open=target_dt,
                open=1.0, high=1.0, low=1.0, close=1.0,
                volume=0.0, pre_market=None, after_hours=None,
            )

        target = (date or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo("America/New_York")).date()
        async with self._semaphore:
            with logfire.span("massive.api.daily_open_close {symbol.ticker}", symbol=symbol):
                result = await asyncio.to_thread(
                    self._client.get_daily_open_close_agg,
                    ticker=symbol.lookup_symbol,
                    date=target,
                )

        if not isinstance(result, DailyOpenCloseAgg):
            return None
        if result.status != "OK":
            return None
        if None in (result.open, result.high, result.low, result.volume):
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

    @logfire.instrument("massive.get_daily_range {symbol.ticker}")
    async def get_daily_range(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
    ) -> list[DailyOpenCloseAggregate]:
        """Return daily OHLCV bars for the given date range."""
        if symbol.is_base_currency:
            return []

        async with self._semaphore:
            with logfire.span("massive.api.get_aggs_daily {symbol.ticker}", symbol=symbol):
                aggs = await asyncio.to_thread(
                    self._client.get_aggs,
                    ticker=symbol.lookup_symbol,
                    multiplier=1,
                    timespan="day",
                    from_=from_,
                    to=to,
                    limit=500,
                )

        if not isinstance(aggs, list):
            return []

        result: list[DailyOpenCloseAggregate] = []
        for agg in aggs:
            if None in (agg.timestamp, agg.open, agg.high, agg.low, agg.close, agg.volume):
                continue
            dt_utc = datetime.fromtimestamp(agg.timestamp / 1000, ZoneInfo("UTC"))
            date_str = dt_utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            date_open = eastern_midnight(date_str)
            result.append(DailyOpenCloseAggregate(
                symbol=symbol,
                date_open=date_open,
                open=agg.open,
                high=agg.high,
                low=agg.low,
                close=agg.close,
                volume=agg.volume,
                pre_market=None,
                after_hours=None,
            ))

        return result

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _fetch_aggs(
        self,
        symbol: AssetSymbol,
        from_: datetime,
        to: datetime,
        *,
        timespan: str = "minute",
        multiplier: int = 1,
        limit: int | None = None,
    ) -> list[Aggregate]:
        """Single-attempt fetch; raises on error."""
        if symbol.is_base_currency:
            return []

        kwargs: dict = dict(
            ticker=symbol.lookup_symbol,
            multiplier=multiplier,
            timespan=timespan,
            from_=from_,
            to=to,
        )
        if limit is not None:
            kwargs["limit"] = limit

        async with self._semaphore:
            with logfire.span("massive.api.get_aggs {symbol.ticker}", symbol=symbol):
                raw: list[Agg] | HTTPResponse | None = await asyncio.to_thread(
                    self._client.get_aggs, **kwargs
                )

        if not isinstance(raw, list):
            return []

        result: list[Aggregate] = []
        for agg in raw:
            if None in (agg.timestamp, agg.open, agg.high, agg.low, agg.close, agg.volume):
                continue
            result.append(Aggregate(
                symbol,
                _ts_to_dt(agg.timestamp),
                agg.open,
                agg.high,
                agg.low,
                agg.close,
                agg.volume,
                timedelta(minutes=1),
            ))
        return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts_to_dt(timestamp: int | float) -> datetime:
    return datetime.fromtimestamp(timestamp / 1000, ZoneInfo("UTC"))
