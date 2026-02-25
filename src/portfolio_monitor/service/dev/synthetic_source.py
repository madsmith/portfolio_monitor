import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.service.types import AssetSymbol

from .price_generator import PriceGenerator, Regime

logger = logging.getLogger(__name__)


class SyntheticDataSource:
    """Generates synthetic market data and publishes AggregateUpdated events."""

    def __init__(
        self,
        bus: EventBus,
        symbols: list[AssetSymbol],
        seed_prices: dict[str, float],
        tick_interval: float = 5.0,
    ) -> None:
        self._bus: EventBus = bus
        self._symbols: list[AssetSymbol] = symbols
        self._tick_interval: float = tick_interval
        self._generator: PriceGenerator = PriceGenerator(tick_interval)
        self._running: bool = False
        self._paused: bool = False
        self._task: asyncio.Task | None = None
        self._tick_event: asyncio.Event = asyncio.Event()
        self._tick_event.set()  # not paused initially

        self._last_tick_time: datetime | None = None
        self._next_tick_time: datetime | None = None
        self._tick_count: int = 0

        for symbol in symbols:
            price = seed_prices.get(symbol.ticker, 100.0)
            self._generator.register_symbol(symbol.ticker, price)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tick_interval(self) -> float:
        return self._tick_interval

    @tick_interval.setter
    def tick_interval(self, value: float) -> None:
        self._tick_interval = max(0.5, value)
        self._generator.tick_interval = self._tick_interval

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def last_tick_time(self) -> datetime | None:
        return self._last_tick_time

    @property
    def next_tick_time(self) -> datetime | None:
        return self._next_tick_time

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def generator(self) -> PriceGenerator:
        return self._generator

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def pause(self) -> None:
        self._paused = True
        self._tick_event.clear()

    def resume(self) -> None:
        self._paused = False
        self._tick_event.set()

    def set_bias(self, ticker: str, bias_pct: float) -> None:
        """Add a decaying bias. bias_pct is in percent (e.g. 3 means +3%).

        Stacks with existing bias. Decays over 3-7 ticks.
        """
        self._generator.add_bias(ticker, bias_pct / 100.0)

    def set_regime(self, regime: Regime) -> None:
        self._generator.set_global_regime(regime)

    def set_symbol_regime(self, ticker: str, regime: Regime) -> None:
        self._generator.set_regime(ticker, regime)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(
            "SyntheticDataSource started (tick_interval=%.1fs, %d symbols)",
            self._tick_interval,
            len(self._symbols),
        )

    async def stop(self) -> None:
        self._running = False
        self._tick_event.set()  # unblock if paused
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("SyntheticDataSource stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        try:
            while self._running:
                await self._tick_event.wait()
                if not self._running:
                    break

                now = datetime.now(ZoneInfo("UTC"))
                self._last_tick_time = now
                self._next_tick_time = now + timedelta(seconds=self._tick_interval)
                self._tick_count += 1

                for symbol in self._symbols:
                    open_, high, low, close, volume = self._generator.tick(symbol.ticker)
                    agg = Aggregate(
                        symbol=symbol,
                        date_open=now,
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        timespan=timedelta(seconds=self._tick_interval),
                    )
                    await self._bus.publish(
                        AggregateUpdated(symbol=symbol, aggregate=agg)
                    )

                await asyncio.sleep(self._tick_interval)
        except asyncio.CancelledError:
            logger.debug("Synthetic data source loop cancelled")

    # ------------------------------------------------------------------
    # History generation for priming
    # ------------------------------------------------------------------

    def generate_history(self, minutes: int) -> list[Aggregate]:
        """Pre-generate minute-bar history for detector priming.

        Returns aggregates in chronological order. Does NOT publish
        them to the bus.
        """
        all_aggs: list[Aggregate] = []
        now = datetime.now(ZoneInfo("UTC"))
        start = now - timedelta(minutes=minutes)

        # Temporarily use 1-minute dt
        saved_interval = self._generator.tick_interval
        self._generator.tick_interval = 60

        for i in range(minutes):
            t = start + timedelta(minutes=i)
            for symbol in self._symbols:
                open_, high, low, close, volume = self._generator.tick(symbol.ticker)
                agg = Aggregate(
                    symbol=symbol,
                    date_open=t,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    timespan=timedelta(minutes=1),
                )
                all_aggs.append(agg)

        # Restore original tick interval
        self._generator.tick_interval = saved_interval
        return all_aggs
