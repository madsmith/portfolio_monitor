import logging
from collections import deque
from datetime import datetime, timedelta

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.data.provider import DataProvider
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.detectors.engine import DeviationEngine
from portfolio_monitor.detectors.events import AlertFired
from portfolio_monitor.service.types import AssetSymbol

logger = logging.getLogger(__name__)


class DetectionService:
    """Runs detectors against incoming aggregates and publishes alerts.

    Subscribes to AggregateUpdated, publishes AlertFired.
    Maintains a bounded log of recent alerts for querying.
    """

    def __init__(
        self,
        bus: EventBus,
        detection_engine: DeviationEngine,
        data_provider: DataProvider | None = None,
        max_alert_history: int = 1000,
    ) -> None:
        self._bus: EventBus = bus
        self._detection_engine: DeviationEngine = detection_engine
        self._data_provider: DataProvider | None = data_provider
        self._alert_log: deque[Alert] = deque(maxlen=max_alert_history)

        self._bus.subscribe(AggregateUpdated, self._on_aggregate_updated)

    async def prime(self, symbols: list[AssetSymbol], end: datetime) -> None:
        """Fetch historical data to warm up detectors, then clear cooldowns."""
        if self._data_provider is None:
            raise RuntimeError("Cannot prime without a DataProvider")

        start: datetime | None = self._detection_engine.preload_data_age(
            end, timedelta(minutes=1)
        )
        if start is None:
            return

        logger.info("Priming detection engine: %s to %s", start, end)
        for symbol in symbols:
            logger.debug("Fetching historical aggregates for %s", symbol)
            aggs: list[Aggregate] = await self._data_provider.get_range(
                symbol, start, end, cache_write=True
            )
            for agg in aggs:
                # Discard detections during prime
                self._detection_engine.detect(agg)

        self._detection_engine.clear_cooldowns()
        logger.info("Detection engine primed")

    def get_recent_alerts(self, n: int = 50) -> list[Alert]:
        """Return the most recent n alerts."""
        return list(self._alert_log)[-n:]

    def get_alerts_for(self, symbol: AssetSymbol) -> list[Alert]:
        """Return all stored alerts for a given symbol."""
        return [a for a in self._alert_log if a.ticker == symbol]

    #######################################################
    # Event Bus Callbacks
    #######################################################

    async def _on_aggregate_updated(self, event: AggregateUpdated) -> None:
        alerts: list[Alert] = self._detection_engine.detect(event.aggregate)
        for alert in alerts:
            logger.warning("Alert: %s", alert)
            self._alert_log.append(alert)
            await self._bus.publish(AlertFired(alert=alert))
