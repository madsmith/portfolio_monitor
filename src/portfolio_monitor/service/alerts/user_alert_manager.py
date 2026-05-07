import logging

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data.database.alerts import AlertChannelSub, AlertsModule
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.detectors.events import AlertCleared, AlertFired, AlertUpdated
from portfolio_monitor.service.alerts.events import UserAlertDeletedEvent, UserAlertsClearedEvent
from portfolio_monitor.service.alerts.channel_pool import ChannelPool
from portfolio_monitor.service.alerts.delivery import AlertDelivery
from portfolio_monitor.service.alerts.delivery.base import AlertEventType

logger = logging.getLogger(__name__)


class UserAlertManager:
    """Routes alerts to delivery backends.

    Subscribes to AlertFired/Updated/Cleared and fans out to:
      1. Global targets (LoggingAlertDelivery, etc.) — all non-suppressed alerts
      2. Implicit per-user deliveries (e.g. DashboardBufferDelivery) — called
         with target=username for every alert that has a known owner
      3. Per-user DB-configured channel subscriptions via ChannelPool
    """

    def __init__(
        self,
        bus: EventBus,
        alerts_module: AlertsModule | None = None,
        channel_pool: ChannelPool | None = None,
        account_store: object = None,
        default_admin_username: str = "default",
    ) -> None:
        self._bus: EventBus = bus
        self._alerts_module: AlertsModule | None = alerts_module
        self._channel_pool: ChannelPool = channel_pool or ChannelPool()

        # detector_id → username, populated by AlertConfigAdapter
        self._detector_username: dict[str, str] = {}
        # detector_id → rule_id, populated by AlertConfigAdapter (for opt_in mode checks)
        self._detector_rule: dict[str, str] = {}

        # Global delivery targets — receive every non-suppressed alert
        self._global_targets: list[AlertDelivery] = []

        # Implicit per-user deliveries — called with target=username for every user alert
        self._implicit_per_user_deliveries: list[AlertDelivery] = []

        # dev-mode: suppress delivery by detector kind
        self.suppressed_detectors: set[str] = set()

        self._bus.subscribe(AlertFired, self._on_alert_fired)
        self._bus.subscribe(AlertUpdated, self._on_alert_updated)
        self._bus.subscribe(AlertCleared, self._on_alert_cleared)
        self._bus.subscribe(UserAlertsClearedEvent, self._on_alerts_cleared_by_user)
        self._bus.subscribe(UserAlertDeletedEvent, self._on_alert_deleted_by_user)

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

    def add_implicit_delivery(self, delivery: AlertDelivery) -> None:
        self._implicit_per_user_deliveries.append(delivery)

    # ------------------------------------------------------------------
    # Detector–user and detector–rule wiring
    # ------------------------------------------------------------------

    def register_detector_account(self, detector_id: str, username: str) -> None:
        self._detector_username[detector_id] = username

    def unregister_detector_account(self, detector_id: str) -> None:
        self._detector_username.pop(detector_id, None)

    def register_detector_rule(self, detector_id: str, rule_id: str) -> None:
        self._detector_rule[detector_id] = rule_id

    def unregister_detector_rule(self, detector_id: str) -> None:
        self._detector_rule.pop(detector_id, None)

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

    async def disconnect_all(self) -> None:
        for target in self._global_targets:
            await target.disconnect()
        await self._channel_pool.disconnect_all()

    # ------------------------------------------------------------------
    # Event bus callbacks
    # ------------------------------------------------------------------

    async def _on_alert_fired(self, event: AlertFired) -> None:
        await self._fan_out(event.alert, AlertEventType.FIRED)

    async def _on_alert_updated(self, event: AlertUpdated) -> None:
        await self._fan_out(event.alert, AlertEventType.UPDATED)

    async def _on_alert_cleared(self, event: AlertCleared) -> None:
        await self._fan_out(event.alert, AlertEventType.CLEARED)

    async def _on_alert_deleted_by_user(self, event: UserAlertDeletedEvent) -> None:
        if self._alerts_module is None:
            return
        subs = self._alerts_module.get_subscriptions(event.username)
        for sub in subs:
            config = self._alerts_module.get_channel_config(sub.channel_config_id)
            if config is None:
                continue
            delivery = await self._channel_pool.ensure_connected(config.type, config.config)
            if delivery is None:
                continue
            if hasattr(delivery, "redact_for_alert"):
                try:
                    await delivery.redact_for_alert(sub.target, event.alert_id)
                except Exception:
                    logger.exception("single redact failed type=%r target=%s", config.type, sub.target)

    async def _on_alerts_cleared_by_user(self, event: UserAlertsClearedEvent) -> None:
        if self._alerts_module is None:
            return
        subs = self._alerts_module.get_subscriptions(event.username)
        for sub in subs:
            config = self._alerts_module.get_channel_config(sub.channel_config_id)
            if config is None:
                continue
            delivery = await self._channel_pool.ensure_connected(config.type, config.config)
            if delivery is None:
                continue
            if hasattr(delivery, "clear_for_target"):
                try:
                    await delivery.clear_for_target(sub.target)
                except Exception:
                    logger.exception("bulk clear failed type=%r target=%s", config.type, sub.target)

    # ------------------------------------------------------------------
    # Delivery helpers
    # ------------------------------------------------------------------

    def _should_deliver(self, sub: AlertChannelSub, rule_id: str | None) -> bool:
        if sub.mode == "off":
            return False
        if sub.mode == "default":
            return True
        # opt_in: only deliver if this rule explicitly opted this subscription in
        if rule_id is None or self._alerts_module is None:
            return False
        return self._alerts_module.has_rule_channel_override(rule_id, sub.id)

    async def _fan_out(self, alert: Alert, event: AlertEventType) -> None:
        if alert.kind in self.suppressed_detectors:
            return

        for target in self._global_targets:
            try:
                await target.send_alert(alert, event=event)
            except Exception:
                logger.exception("Error delivering alert to global target %s", target)

        username = self._detector_username.get(alert.detector_id)
        if not username:
            return

        for delivery in self._implicit_per_user_deliveries:
            try:
                await delivery.send_alert(alert, target=username, event=event)
            except Exception:
                logger.exception("Error delivering alert via implicit delivery %s", delivery)

        if self._alerts_module is None:
            return

        rule_id = self._detector_rule.get(alert.detector_id)
        subs = self._alerts_module.get_subscriptions(username)
        for sub in subs:
            if not self._should_deliver(sub, rule_id):
                continue
            config = self._alerts_module.get_channel_config(sub.channel_config_id)
            if config is None:
                continue
            delivery = await self._channel_pool.ensure_connected(config.type, config.config)
            if delivery is None:
                continue
            try:
                await delivery.send_alert(alert, target=sub.target, event=event)
            except Exception:
                logger.exception(
                    "Channel delivery failed type=%r target=%s", config.type, sub.target
                )
