from __future__ import annotations

from typing import TYPE_CHECKING

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import DataProvider
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.detectors import DeviationEngine
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.service.alerts.user_alert_manager import UserAlertManager
from portfolio_monitor.service.monitor import MonitorService
from portfolio_monitor.service.types import AssetSymbol
from portfolio_monitor.watchlist.events import (
    WatchlistEntryAdded,
    WatchlistEntryRemoved,
)

if TYPE_CHECKING:
    from portfolio_monitor.service.event_hooks.alert_adapter import AlertConfigAdapter


class WatchlistAdapter:
    """Keeps the DeviationEngine and MonitorService in sync with watchlist entry changes."""

    def __init__(
        self,
        engine: DeviationEngine,
        alert_manager: UserAlertManager,
        monitor: MonitorService,
        detection_service: DetectionService,
        data_provider: DataProvider,
        alert_adapter: AlertConfigAdapter,
    ) -> None:
        self._engine: DeviationEngine = engine
        self._alert_manager: UserAlertManager = alert_manager
        self._monitor: MonitorService = monitor
        self._detection_service: DetectionService = detection_service
        self._data_provider: DataProvider = data_provider
        self._alert_adapter: AlertConfigAdapter = alert_adapter
        self._bus: EventBus | None = None

    def wire(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(WatchlistEntryAdded, self.on_entry_added)
        bus.subscribe(WatchlistEntryRemoved, self.on_entry_removed)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_entry_added(self, event: WatchlistEntryAdded) -> None:
        self._monitor.register_symbol(event.symbol)
        agg = await self._data_provider.get_aggregate(event.symbol)
        if agg and self._bus is not None:
            await self._bus.publish(AggregateUpdated(symbol=event.symbol, aggregate=agg))
        self._alert_adapter.apply_rules_to_symbol(event.symbol, event.owner)

    async def on_entry_removed(self, event: WatchlistEntryRemoved) -> None:
        self._alert_adapter.remove_rules_from_symbol(event.symbol, event.owner)

