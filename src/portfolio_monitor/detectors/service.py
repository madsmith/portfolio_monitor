from datetime import datetime, timedelta

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import AggregateUpdated, DataProvider
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.detectors.engine import AlertChange, DeviationEngine
from portfolio_monitor.detectors.events import AlertCleared, AlertFired, AlertUpdated
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.utils import get_trace_logger

logger = get_trace_logger(__name__)


class DetectionService:
    """Runs detectors against incoming aggregates and publishes alert lifecycle events.

    Subscribes to AggregateUpdated, publishes AlertFired / AlertUpdated / AlertCleared.
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

        # Keyed by alert id for O(1) updates; preserves insertion order (Python 3.7+)
        self._alert_log: dict[str, Alert] = {}
        self._max_alert_history: int = max_alert_history

        self._bus.subscribe(AggregateUpdated, self._on_aggregate_updated)

    async def prime(
        self,
        symbols: list[AssetSymbol],
        current_time: datetime,
        sample_interval: timedelta = timedelta(minutes=1),
    ) -> None:
        """Prime all detectors for the given symbols."""
        if self._data_provider is None:
            raise RuntimeError("Cannot prime without a DataProvider")
        logger.info("Priming detection engine for %d symbols", len(symbols))
        await self._detection_engine.prime(
            symbols, self._data_provider, current_time, sample_interval
        )
        logger.info("Detection engine primed")

    def get_recent_alerts(self, n: int = 50) -> list[Alert]:
        """Return the most recent n alerts (fired or updated)."""
        alerts = list(self._alert_log.values())
        return alerts[-n:]

    def clear_alerts(self) -> None:
        """Clear all stored alerts."""
        self._alert_log.clear()

    def get_alerts_for(self, symbol: AssetSymbol) -> list[Alert]:
        """Return all stored alerts for a given symbol."""
        return [a for a in self._alert_log.values() if a.ticker == symbol]

    def get_active_alerts(self) -> list[Alert]:
        """Return currently active alerts from the engine."""
        return self._detection_engine.get_active_alerts()

    #######################################################
    # Event Bus Callbacks
    #######################################################

    async def _on_aggregate_updated(self, event: AggregateUpdated) -> None:
        changes: list[AlertChange] = self._detection_engine.detect(event.aggregate)
        for change in changes:
            alert = change.alert
            if change.kind == "fired":
                self._add_to_log(alert)
                logger.trace("Alert fired: %s", alert)
                await self._bus.publish(AlertFired(alert=alert))
            elif change.kind == "updated":
                self._update_in_log(alert)
                logger.trace("Alert updated: %s", alert)
                await self._bus.publish(AlertUpdated(alert=alert))
            elif change.kind == "cleared":
                logger.trace("Alert cleared: %s", alert)
                await self._bus.publish(AlertCleared(alert=alert))

    def _add_to_log(self, alert: Alert) -> None:
        if len(self._alert_log) >= self._max_alert_history:
            # Remove oldest entry
            oldest_key = next(iter(self._alert_log))
            del self._alert_log[oldest_key]
        self._alert_log[alert.id] = alert

    def _update_in_log(self, alert: Alert) -> None:
        self._alert_log[alert.id] = alert
