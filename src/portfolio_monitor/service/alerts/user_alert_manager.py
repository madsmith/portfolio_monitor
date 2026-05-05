import logging

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.detectors.events import AlertCleared, AlertFired, AlertUpdated
from portfolio_monitor.service.alerts.buffer import AlertBufferStore
from portfolio_monitor.service.alerts.delivery import AlertDelivery
from portfolio_monitor.service.alerts.delivery.matrix import MatrixDelivery
from portfolio_monitor.service.alerts.models import ChannelConfig, UserAlertConfig
from portfolio_monitor.service.settings.account_store import AccountStore

logger = logging.getLogger(__name__)


class UserAlertManager:
    """Routes alerts to delivery backends using per-user UserAlertConfig.

    Subscribes to AlertFired/Updated/Cleared events and fans out to:
      1. Global targets (LoggingAlertDelivery, openclaw, etc.) — all alerts
      2. Per-user channel targets — resolved from each user's effective_channels()

    Channel-specific delivery (dashboard buffer, Matrix) is added in later phases;
    the routing infrastructure is wired here.
    """

    def __init__(
        self,
        bus: EventBus,
        account_store: AccountStore,
        default_admin_username: str,
        alert_buffer_store: AlertBufferStore | None = None,
    ) -> None:
        self._bus: EventBus = bus
        self._account_store: AccountStore = account_store
        self._default_admin_username: str = default_admin_username
        self._alert_buffer_store: AlertBufferStore | None = alert_buffer_store
        # (username, channel_name) → connected MatrixDelivery instance
        self._matrix_deliveries: dict[tuple[str, str], MatrixDelivery] = {}

        # detector_id → username, built alongside DeviationEngine
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
    # User config lookup
    # ------------------------------------------------------------------

    def _get_user_config(self, username: str) -> UserAlertConfig:
        if username == self._default_admin_username:
            return self._account_store.get_default_admin_alert_config()
        account = self._account_store.get(username)
        return account.alert_config if account else UserAlertConfig()

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
        for delivery in self._matrix_deliveries.values():
            await delivery.disconnect()
        self._matrix_deliveries.clear()

    # ------------------------------------------------------------------
    # Event bus callbacks
    # ------------------------------------------------------------------

    async def _on_alert_fired(self, event: AlertFired) -> None:
        print(" >> Fanning out alert", event.alert)  # TODO: remove
        await self._fan_out(event.alert, update_buffer=True)

    async def _on_alert_updated(self, event: AlertUpdated) -> None:
        print(" >> Fanning out alert update", event.alert)  # TODO: remove
        await self._fan_out(event.alert, update_buffer=True)

    async def _on_alert_cleared(self, event: AlertCleared) -> None:
        await self._fan_out(event.alert, update_buffer=False)

    async def _fan_out(self, alert: Alert, update_buffer: bool = True) -> None:
        if alert.kind in self.suppressed_detectors:
            print(" >> Suppressed alert", alert)  # TODO: remove
            return

        for target in self._global_targets:
            try:
                print(" >> Sending alert to global target", target)  # TODO: remove
                await target.send_alert(alert)
            except Exception:
                logger.exception("Error delivering alert to global target %s", target)

        username = self._detector_username.get(alert.detector_id)
        if not username:
            print("  !!!!  No username found for detector", alert.detector_id)  # TODO: remove
            return

        if update_buffer and self._alert_buffer_store is not None:
            print("  !!!!  Pushing alert to buffer", alert, "for user", username)  # TODO: remove
            self._alert_buffer_store.get_or_create(username).push(alert.to_dict())

        config = self._get_user_config(username)
        matching_rule = next(
            (
                r for r in config.rules
                if r.kind == alert.kind
                and (r.ticker == "" or r.ticker == alert.ticker.ticker)
            ),
            None,
        )
        if matching_rule is None:
            return

        for channel in config.effective_channels(matching_rule):
            await self._deliver_to_channel(alert, username, channel)

    async def _deliver_to_channel(
        self, alert: Alert, username: str, channel: ChannelConfig
    ) -> None:
        if channel.type == "matrix":
            delivery = await self._get_matrix_delivery(username, channel)
            if delivery is not None:
                try:
                    await delivery.send_alert(alert)
                except Exception:
                    logger.exception("Matrix delivery error for user %s channel %s", username, channel.name)

    async def _get_matrix_delivery(
        self, username: str, channel: ChannelConfig
    ) -> MatrixDelivery | None:
        key = (username, channel.name)
        if key not in self._matrix_deliveries:
            try:
                d = MatrixDelivery.from_channel_params(channel.params)
                await d.connect()
                self._matrix_deliveries[key] = d
            except (KeyError, Exception):
                logger.exception("Failed to init Matrix delivery for user %s channel %s", username, channel.name)
                return None
        return self._matrix_deliveries[key]
