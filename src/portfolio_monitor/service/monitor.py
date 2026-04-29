import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import logfire

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import Aggregate, AggregateUpdated, DataProvider, MarketInfo
from portfolio_monitor.utils import logfire_set_attribute
from portfolio_monitor.portfolio import PortfolioService
from portfolio_monitor.service.types import AssetSymbol, AssetUpdateRecord

logger = logging.getLogger(__name__)


class MonitorService:
    """Poll loop that fetches market data and publishes AggregateUpdated events."""

    def __init__(
        self,
        bus: EventBus,
        data_provider: DataProvider,
        portfolio_service: PortfolioService
    ) -> None:
        self._bus: EventBus = bus
        self._data_provider: DataProvider = data_provider
        self._portfolio_service: PortfolioService = portfolio_service

        self.running: bool = False
        self._task: asyncio.Task | None = None
        self._symbols: dict[AssetSymbol, AssetUpdateRecord] = {}

    @property
    def task(self) -> asyncio.Task | None:
        return self._task

    async def start(self) -> None:
        if self.running:
            logger.warning("Monitor service is already running")
            return

        self.running = True
        logger.info("Starting monitor")
        self._task = asyncio.create_task(self._run())

    def register_symbol(self, symbol: AssetSymbol) -> None:
        """Add a symbol to the monitor poll set (live, no restart needed)."""
        if symbol not in self._symbols:
            self._symbols[symbol] = AssetUpdateRecord(symbol)

    def unregister_symbol(self, symbol: AssetSymbol) -> None:
        """Remove a symbol from the monitor poll set."""
        self._symbols.pop(symbol, None)

    async def stop(self) -> None:
        if not self.running:
            logger.warning("Monitor service is not running")
            return

        logger.info("Stopping monitor")
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Monitor stopped")

    async def _run(self) -> None:
        update_interval = timedelta(seconds=60)

        # Build initial symbol set from portfolios
        self._symbols = {
            asset.symbol: AssetUpdateRecord(asset.symbol)
            for portfolio in self._portfolio_service.get_all_portfolios()
            for asset in portfolio.assets()
        }

        try:
            while self.running:
                now: datetime = datetime.now(ZoneInfo("UTC"))
                next_update = await self._tick(now, update_interval)

                sleep_seconds = max(
                    (next_update - now).total_seconds(),
                    update_interval.total_seconds() / 2,
                )
                logger.debug(
                    "Monitor sleeping %.1f seconds (%d symbols tracked)",
                    sleep_seconds,
                    len(self._symbols),
                )
                await asyncio.sleep(sleep_seconds)

        except asyncio.CancelledError:
            logger.debug("Monitor loop cancelled")
            raise
        except Exception:
            logger.exception("Error in monitor loop")
            self.running = False

    @logfire.instrument("monitor.tick")
    async def _tick(self, now: datetime, update_interval: timedelta) -> datetime:
        # TODO: add option to offset data by configurable delay to support limited access to realtime data (e.g. 15-minute delayed data from Polygon free tier)
        next_update = now + update_interval

        # Determine which symbols are due for an update
        due_records: list[AssetUpdateRecord] = []
        for record in self._symbols.values():
            if not MarketInfo.is_market_open(record.symbol, now):
                continue
            if record.time_updated and now <= record.time_updated + update_interval:
                logger.debug("Skipping update for %s - too soon", record.symbol)
                next_update = min(next_update, record.time_updated + update_interval)
                continue
            due_records.append(record)

        logfire_set_attribute("symbol_count", len(self._symbols))
        logfire_set_attribute("symbols_polled", len(due_records))

        # Fetch all due symbols concurrently; rate limiting is enforced inside the provider
        results = await asyncio.gather(
            *[self._data_provider.get_aggregate(r.symbol) for r in due_records],
            return_exceptions=True,
        )

        for record, result in zip(due_records, results):
            if isinstance(result, Exception):
                logger.warning("Error fetching aggregate for %s: %s", record.symbol, result)
                continue
            if result:
                record.time_updated = result.date_open + result.timespan
                next_update = min(next_update, record.time_updated + update_interval)
                await self._bus.publish(AggregateUpdated(symbol=record.symbol, aggregate=result))

        return next_update
