from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.database.alerts import AlertsModule
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.service.alerts.events import AlertStatusEvent
from .base import AlertEventType


class DashboardBufferDelivery:
    """Persists alerts to the DB and publishes AlertStatusEvent for WS push.

    target is the owning username. CLEARED events are ignored — the record
    stays in DB and the user dismisses it via the dashboard.
    """

    def __init__(self, alerts_module: AlertsModule, bus: EventBus) -> None:
        self._alerts_module: AlertsModule = alerts_module
        self._bus: EventBus = bus

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def send_alert(
        self,
        alert: Alert,
        *,
        target: str = "",
        event: AlertEventType = AlertEventType.FIRED,
    ) -> None:
        if event == AlertEventType.CLEARED or not target:
            return
        record, is_new = self._alerts_module.push_record(target, alert.to_dict())
        if record.deleted:
            return
        unread_count = self._alerts_module.get_unread_count(target)
        await self._bus.publish(AlertStatusEvent(
            username=target,
            payload={
                "event": "fired" if is_new else "updated",
                "alert": record.to_dict(),
                "unread_count": unread_count,
            },
        ))
