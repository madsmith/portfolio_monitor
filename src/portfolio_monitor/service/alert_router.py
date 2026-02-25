import logging

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.detectors.events import AlertFired
from portfolio_monitor.service.alerts import AlertDelivery

logger = logging.getLogger(__name__)


class AlertRouter:
    """Routes alerts to registered delivery backends.

    Subscribes to AlertFired events and fans out to all
    registered AlertDelivery targets.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus: EventBus = bus
        self._targets: list[AlertDelivery] = []

        self._bus.subscribe(AlertFired, self._on_alert_fired)

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

    async def _on_alert_fired(self, event: AlertFired) -> None:
        for target in self._targets:
            try:
                await target.send_alert(event.alert)
            except Exception:
                logger.exception(
                    "Error delivering alert to %s",
                    target,
                )
