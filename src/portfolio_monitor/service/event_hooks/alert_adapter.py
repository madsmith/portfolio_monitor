from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.detectors import DeviationEngine, DetectorRegistry
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.portfolio import PortfolioService
from portfolio_monitor.service.alerts.models import AlertRule
from portfolio_monitor.service.alerts.rule_events import AlertRuleAdded, AlertRuleRemoved, AlertRuleUpdated
from portfolio_monitor.service.alerts.user_alert_manager import UserAlertManager
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.watchlist.service import WatchlistService


class AlertConfigAdapter:
    """Keeps the running DeviationEngine in sync when alert rules are added, updated, or removed via the API."""

    def __init__(
        self,
        engine: DeviationEngine,
        alert_manager: UserAlertManager,
        detection_service: DetectionService,
        portfolio_service: PortfolioService,
        watchlist_service: WatchlistService,
    ) -> None:
        self._engine: DeviationEngine = engine
        self._alert_manager: UserAlertManager = alert_manager
        self._detection_service: DetectionService = detection_service
        self._portfolio_service: PortfolioService = portfolio_service
        self._watchlist_service: WatchlistService = watchlist_service

    def wire(self, bus: EventBus) -> None:
        bus.subscribe(AlertRuleAdded, self.on_alert_added)
        bus.subscribe(AlertRuleRemoved, self.on_alert_removed)
        bus.subscribe(AlertRuleUpdated, self.on_alert_updated)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_alert_added(self, event: AlertRuleAdded) -> None:
        self._add_alert(event.username, event.rule)
        symbols = self._symbols_for_alert(event.rule)
        if symbols:
            await self._detection_service.prime(symbols, datetime.now(ZoneInfo("UTC")))

    async def on_alert_removed(self, event: AlertRuleRemoved) -> None:
        self._remove_alert(event.username, event.rule)

    async def on_alert_updated(self, event: AlertRuleUpdated) -> None:
        self._remove_alert(event.username, event.old_rule)
        self._add_alert(event.username, event.new_rule)
        symbols = self._symbols_for_alert(event.new_rule)
        if symbols:
            await self._detection_service.prime(symbols, datetime.now(ZoneInfo("UTC")))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _all_symbols(self) -> list[AssetSymbol]:
        return list(
            {asset.symbol for portfolio in self._portfolio_service.get_all_portfolios() for asset in portfolio.assets()}
            | {entry.symbol for wl in self._watchlist_service.get_all_watchlists() for entry in wl.entries}
        )

    def _symbols_for_alert(self, alert: AlertRule) -> list[AssetSymbol]:
        if alert.ticker:
            sym = next((s for s in self._all_symbols() if s.ticker == alert.ticker), None)
            return [sym] if sym else []
        return self._all_symbols()

    def _add_alert(self, username: str, alert: AlertRule) -> None:
        detector = DetectorRegistry.create_detector(alert.kind, alert.args)
        if detector is None:
            return
        for symbol in self._symbols_for_alert(alert):
            self._engine.add_detector(symbol, detector)  # type: ignore[arg-type]
        self._alert_manager.register_detector_account(detector.detector_id, username)

    def _remove_alert(self, username: str, alert: AlertRule) -> None:
        for symbol in self._symbols_for_alert(alert):
            detector_ids = [
                d.detector_id for d in self._engine.asset_detectors.get(symbol, [])
                if self._alert_manager._detector_username.get(d.detector_id) == username
                and d.name() == alert.kind
            ]
            for detector_id in detector_ids:
                self._engine.remove_detector(symbol, detector_id)
                self._alert_manager.unregister_detector_account(detector_id)
