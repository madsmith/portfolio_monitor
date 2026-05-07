import logging

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.database.alerts import AlertsModule
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.detectors.events import AlertCleared, AlertFired, AlertUpdated
from portfolio_monitor.service.alerts.buffer import AlertBufferStore
from portfolio_monitor.service.alerts.channel_pool import ChannelPool
from portfolio_monitor.service.alerts.delivery import AlertDelivery

logger = logging.getLogger(__name__)


class UserAlertManager:
    """Routes alerts to delivery backends.

    Subscribes to AlertFired/Updated/Cleared and fans out to:
      1. Global targets (LoggingAlertDelivery, etc.) — all non-suppressed alerts
      2. Per-user DB-configured channels via ChannelPool
      3. Per-user dashboard buffer (AlertBufferStore)
    """

    def __init__(
        self,
        bus: EventBus,
        alert_buffer_store: AlertBufferStore | None = None,
        alerts_module: AlertsModule | None = None,
        channel_pool: ChannelPool | None = None,
        # kept for call-site compatibility during transition
        account_store: object = None,
        default_admin_username: str = "default",
    ) -> None:
        self._bus: EventBus = bus
        self._alert_buffer_store: AlertBufferStore | None = alert_buffer_store
        self._alerts_module: AlertsModule | None = alerts_module
        self._channel_pool: ChannelPool = channel_pool or ChannelPool()

        # detector_id → username, populated by AlertConfigAdapter
        self._detector_username: dict[str, str] = {}

        # Global delivery targets — receive every non-suppressed alert
        self._global_targets: list[AlertDelivery] = []

        # dev-mode: suppress delivery by detector kind
        self.suppressed_detectors: set[str] = set()

        self._bus.subscribe(AlertFired, self._on_alert_fired)
        self._bus.subscribe(AlertUpdated, self._on_alert_updated)
        self._bus.subscribe(AlertCleared, self._on_alert_cleared)

    # ------------------------------------------------------------------
    # Target registration
    # ------------------------------------------------------------------

    def add_global_target(self, target: AlertDelivery) -> None:
        self._global_targets.append(target)

    add_target = add_global_target  # alias

    def remove_target(self, target: AlertDelivery) -> None:
        try:
            self._global_targets.remove(target)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Detector–user wiring
    # ------------------------------------------------------------------

    def register_detector_account(self, detector_id: str, username: str) -> None:
        self._detector_username[detector_id] = username

    def unregister_detector_account(self, detector_id: str) -> None:
        self._detector_username.pop(detector_id, None)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect_all(self) -> None:
        failed: list[AlertDelivery] = []
        for target in self._global_targets:
            try:
                await target.connect()
            except Exception:
                logger.exception("Failed to connect target %s — removing", target)
                failed.append(target)
        for t in failed:
            self._global_targets.remove(t)
        # Pool entries connect lazily via ensure_connected in _fan_out

    async def disconnect_all(self) -> None:
        for target in self._global_targets:
            await target.disconnect()
        await self._channel_pool.disconnect_all()

    # ------------------------------------------------------------------
    # Event bus callbacks
    # ------------------------------------------------------------------

    async def _on_alert_fired(self, event: AlertFired) -> None:
        await self._fan_out(event.alert, update_buffer=True)

    async def _on_alert_updated(self, event: AlertUpdated) -> None:
        await self._fan_out(event.alert, update_buffer=True)

    async def _on_alert_cleared(self, event: AlertCleared) -> None:
        await self._fan_out(event.alert, update_buffer=False)

    async def _fan_out(self, alert: Alert, update_buffer: bool = True) -> None:
        if alert.kind in self.suppressed_detectors:
            return

        for target in self._global_targets:
            try:
                await target.send_alert(alert)
            except Exception:
                logger.exception("Error delivering alert to global target %s", target)

        username = self._detector_username.get(alert.detector_id)
        if not username:
            return

        if update_buffer and self._alert_buffer_store is not None:
            await self._alert_buffer_store.get_or_create(username).push(alert.to_dict())

        if self._alerts_module is None:
            return

        channels = self._alerts_module.get_channels(username)
        for ch in channels:
            if not ch.enabled:
                continue
            delivery = await self._channel_pool.ensure_connected(ch.type, ch.config)
            if delivery is None:
                continue
            try:
                await delivery.send_alert(alert)
            except Exception:
                logger.exception(
                    "Error delivering alert via channel type=%r owner=%s", ch.type, username
                )
