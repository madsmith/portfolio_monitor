from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import DataProvider
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.detectors import DeviationEngine, DetectorRegistry
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.service.alerts.user_alert_manager import UserAlertManager
from portfolio_monitor.service.monitor import MonitorService
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.watchlist.events import (
    WatchlistEntryAdded,
    WatchlistEntryAlertsUpdated,
    WatchlistEntryRemoved,
)


class WatchlistAdapter:
    """Keeps the DeviationEngine and MonitorService in sync with watchlist entry changes."""

    def __init__(
        self,
        engine: DeviationEngine,
        alert_manager: UserAlertManager,
        monitor: MonitorService,
        detection_service: DetectionService,
        data_provider: DataProvider,
    ) -> None:
        self._engine: DeviationEngine = engine
        self._alert_manager: UserAlertManager = alert_manager
        self._monitor: MonitorService = monitor
        self._detection_service: DetectionService = detection_service
        self._data_provider: DataProvider = data_provider
        self._bus: EventBus | None = None
        # (owner, ticker) → detector ids registered for that entry
        self._entry_detectors: dict[tuple[str, str], list[str]] = defaultdict(list)

    def wire(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(WatchlistEntryAdded, self.on_entry_added)
        bus.subscribe(WatchlistEntryRemoved, self.on_entry_removed)
        bus.subscribe(WatchlistEntryAlertsUpdated, self.on_alerts_updated)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_entry_added(self, event: WatchlistEntryAdded) -> None:
        self._monitor.register_symbol(event.symbol)
        # Seed initial price immediately (fallback to prev close when market closed)
        agg = await self._data_provider.get_aggregate(event.symbol)
        if agg and self._bus is not None:
            await self._bus.publish(AggregateUpdated(symbol=event.symbol, aggregate=agg))
        ids = self._add_detectors(event.symbol, event.alert_config, event.owner)
        self._entry_detectors[(event.owner, event.symbol.ticker)].extend(ids)
        if ids:
            await self._detection_service.prime([event.symbol], datetime.now(ZoneInfo("UTC")))

    async def on_entry_removed(self, event: WatchlistEntryRemoved) -> None:
        self._remove_detectors(event.symbol, event.owner)
        # Conservatively keep monitor registration — polling a dead symbol is harmless.

    async def on_alerts_updated(self, event: WatchlistEntryAlertsUpdated) -> None:
        self._remove_detectors(event.symbol, event.owner)
        ids = self._add_detectors(event.symbol, event.new_alert_config, event.owner)
        self._entry_detectors[(event.owner, event.symbol.ticker)].extend(ids)
        if ids:
            await self._detection_service.prime([event.symbol], datetime.now(ZoneInfo("UTC")))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_detectors(self, symbol: AssetSymbol, alert_config: dict, owner: str) -> list[str]:
        ids: list[str] = []
        for kind, args in alert_config.items():
            if not isinstance(args, dict):
                continue
            detector = DetectorRegistry.create_detector(kind, args)
            if detector is None:
                continue
            self._engine.add_detector(symbol, detector)  # type: ignore[arg-type]
            self._alert_manager.register_detector_account(detector.detector_id, owner)
            ids.append(detector.detector_id)
        return ids

    def _remove_detectors(self, symbol: AssetSymbol, owner: str) -> None:
        key = (owner, symbol.ticker)
        for detector_id in self._entry_detectors.pop(key, []):
            self._engine.remove_detector(symbol, detector_id)
            self._alert_manager.unregister_detector_account(detector_id)
