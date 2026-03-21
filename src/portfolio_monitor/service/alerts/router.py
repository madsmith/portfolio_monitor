import logging
from collections import defaultdict

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.detectors.base import Alert
from portfolio_monitor.detectors.events import AlertCleared, AlertFired, AlertUpdated
from portfolio_monitor.service.alerts.delivery import AlertDelivery

logger = logging.getLogger(__name__)


class AlertRouter:
    """Routes alerts to delivery backends.

    Subscribes to AlertFired, AlertUpdated, and AlertCleared events and fans
    out to registered targets.

    Global targets (e.g. LoggingAlertDelivery) receive every non-suppressed alert.

    Per-account targets receive alerts only from detectors registered to that
    account via register_detector_account(). Delivery can be further filtered
    per-account via suppress_for_account().
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus: EventBus = bus
        self._global_targets: list[AlertDelivery] = []
        # detector_id → list of account usernames
        self._detector_accounts: defaultdict[str, list[str]] = defaultdict(list)
        # username → list of delivery targets
        self._account_targets: defaultdict[str, list[AlertDelivery]] = defaultdict(list)
        # username → set of suppressed detector kinds
        self._account_suppressions: defaultdict[str, set[str]] = defaultdict(set)
        # Global suppression by detector kind (used by control panel)
        self.suppressed_detectors: set[str] = set()

        self._bus.subscribe(AlertFired, self._on_alert_fired)
        self._bus.subscribe(AlertUpdated, self._on_alert_updated)
        self._bus.subscribe(AlertCleared, self._on_alert_cleared)

    # ------------------------------------------------------------------
    # Target registration
    # ------------------------------------------------------------------

    def add_global_target(self, target: AlertDelivery) -> None:
        """Register a global delivery target that receives all non-suppressed alerts."""
        self._global_targets.append(target)

    def add_target(self, target: AlertDelivery) -> None:
        """Alias for add_global_target."""
        self.add_global_target(target)

    def remove_target(self, target: AlertDelivery) -> None:
        try:
            self._global_targets.remove(target)
        except ValueError:
            pass

    def add_account_target(self, username: str, target: AlertDelivery) -> None:
        """Register a delivery target for a specific account."""
        self._account_targets[username].append(target)

    def remove_account_target(self, username: str, target: AlertDelivery) -> None:
        """Unregister a delivery target for a specific account."""
        try:
            self._account_targets[username].remove(target)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Detector–account wiring
    # ------------------------------------------------------------------

    def register_detector_account(self, detector_id: str, username: str) -> None:
        """Associate a detector instance with an account username.

        When an alert fires from this detector, it will be routed to the
        account's registered targets.
        """
        self._detector_accounts[detector_id].append(username)

    # ------------------------------------------------------------------
    # Per-account suppression
    # ------------------------------------------------------------------

    def suppress_for_account(self, username: str, kind: str) -> None:
        """Suppress alerts of the given detector kind for a specific account."""
        self._account_suppressions[username].add(kind)

    def unsuppress_for_account(self, username: str, kind: str) -> None:
        """Remove per-account suppression for a detector kind."""
        self._account_suppressions[username].discard(kind)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect_all(self) -> None:
        failed: list[AlertDelivery] = []
        for target in self._global_targets:
            try:
                await target.connect()
            except Exception:
                logger.exception("Failed to connect global target %s — removing", target)
                failed.append(target)
        for t in failed:
            self._global_targets.remove(t)

        for username, targets in self._account_targets.items():
            failed = []
            for target in targets:
                try:
                    await target.connect()
                except Exception:
                    logger.exception(
                        "Failed to connect target %s for account %s — removing", target, username
                    )
                    failed.append(target)
            for t in failed:
                targets.remove(t)

    async def disconnect_all(self) -> None:
        for target in self._global_targets:
            await target.disconnect()
        for targets in self._account_targets.values():
            for target in targets:
                await target.disconnect()

    # ------------------------------------------------------------------
    # Event bus callbacks
    # ------------------------------------------------------------------

    async def _on_alert_fired(self, event: AlertFired) -> None:
        await self._fan_out(event.alert)

    async def _on_alert_updated(self, event: AlertUpdated) -> None:
        await self._fan_out(event.alert)

    async def _on_alert_cleared(self, event: AlertCleared) -> None:
        await self._fan_out(event.alert)

    async def _fan_out(self, alert: Alert) -> None:
        if alert.kind in self.suppressed_detectors:
            return
        for target in self._global_targets:
            try:
                await target.send_alert(alert)
            except Exception:
                logger.exception("Error delivering alert to %s", target)

        for username in self._detector_accounts.get(alert.detector_id, ()):
            if alert.kind in self._account_suppressions.get(username, ()):
                continue
            for target in self._account_targets.get(username, ()):
                try:
                    await target.send_alert(alert)
                except Exception:
                    logger.exception(
                        "Error delivering alert to %s for account %s", target, username
                    )
