import logging

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.detectors.events import AlertCleared, AlertFired, AlertUpdated
from portfolio_monitor.service.alerts.delivery import AlertDelivery

logger = logging.getLogger(__name__)


class AlertRouter:
    """Routes alerts to registered delivery backends.

    Subscribes to AlertFired, AlertUpdated, and AlertCleared events and fans
    out to all registered AlertDelivery targets.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus: EventBus = bus
        self._targets: list[AlertDelivery] = []
        self.suppressed_detectors: set[str] = set()

        self._bus.subscribe(AlertFired, self._on_alert_fired)
        self._bus.subscribe(AlertUpdated, self._on_alert_updated)
        self._bus.subscribe(AlertCleared, self._on_alert_cleared)

    def add_target(self, target: AlertDelivery) -> None:
        self._targets.append(target)

    def remove_target(self, target: AlertDelivery) -> None:
        try:
            self._targets.remove(target)
        except ValueError:
            pass

    async def connect_all(self) -> None:
        for target in self._targets:
            await target.connect()

    async def disconnect_all(self) -> None:
        for target in self._targets:
            await target.disconnect()

    #######################################################
    # Event Bus Callbacks
    #######################################################

    async def _on_alert_fired(self, event: AlertFired) -> None:
        if event.alert.kind in self.suppressed_detectors:
            return
        await self._fan_out(event.alert)

    async def _on_alert_updated(self, event: AlertUpdated) -> None:
        if event.alert.kind in self.suppressed_detectors:
            return
        await self._fan_out(event.alert)

    async def _on_alert_cleared(self, event: AlertCleared) -> None:
        if event.alert.kind in self.suppressed_detectors:
            return
        await self._fan_out(event.alert)

    async def _fan_out(self, alert: object) -> None:
        for target in self._targets:
            try:
                await target.send_alert(alert)  # type: ignore[arg-type]
            except Exception:
                logger.exception("Error delivering alert to %s", target)
