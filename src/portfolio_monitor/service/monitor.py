import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import Aggregate, AggregateUpdated, DataProvider, MarketInfo
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
                next_update = now + update_interval

                # TODO: add option to offset data by configurable delay to support limited access to realtime data (e.g. 15-minute delayed data from Polygon free tier)
                for record in self._symbols.values():
                    symbol: AssetSymbol = record.symbol

                    if not MarketInfo.is_market_open(symbol, now):
                        continue

                    if record.time_updated and now <= record.time_updated + update_interval:
                        logger.debug("Skipping update for %s - too soon", symbol)
                        next_update = min(next_update, record.time_updated + update_interval)
                        continue

                    logger.debug("Updating %s", symbol)
                    aggregate: Aggregate | None = await self._data_provider.get_aggregate(symbol)
                    if aggregate:
                        record.time_updated = aggregate.date_open + aggregate.timespan
                        next_update = min(next_update, record.time_updated + update_interval)
                        await self._bus.publish(
                            AggregateUpdated(symbol=symbol, aggregate=aggregate)
                        )

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
