from __future__ import annotations

from typing import TYPE_CHECKING

from portfolio_monitor.core.events import EventBus
from portfolio_monitor.data import MarketData
from portfolio_monitor.data.events import AggregateUpdated
from portfolio_monitor.detectors import DeviationEngine
from portfolio_monitor.detectors.service import DetectionService
from portfolio_monitor.service.alerts.user_alert_manager import UserAlertManager
from portfolio_monitor.watchlist.events import (
    WatchlistEntryAdded,
    WatchlistEntryRemoved,
)

if TYPE_CHECKING:
    from portfolio_monitor.service.event_hooks.alert_adapter import AlertConfigAdapter


class WatchlistAdapter:
    """Keeps the DeviationEngine and MarketData in sync with watchlist entry changes."""

    def __init__(
        self,
        engine: DeviationEngine,
        alert_manager: UserAlertManager,
        market_data: MarketData,
        detection_service: DetectionService,
        alert_adapter: AlertConfigAdapter,
        bus: EventBus,
    ) -> None:
        self._engine: DeviationEngine = engine
        self._alert_manager: UserAlertManager = alert_manager
        self._market_data: MarketData = market_data
        self._detection_service: DetectionService = detection_service
        self._alert_adapter: AlertConfigAdapter = alert_adapter
        self._bus: EventBus = bus
        
        bus.subscribe(WatchlistEntryAdded, self.on_entry_added)
        bus.subscribe(WatchlistEntryRemoved, self.on_entry_removed)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def on_entry_added(self, event: WatchlistEntryAdded) -> None:
        self._market_data.register_symbol(event.symbol)
        agg = await self._market_data.get_aggregate(event.symbol)
        if agg:
            await self._bus.publish(AggregateUpdated(symbol=event.symbol, aggregate=agg))
        self._alert_adapter.apply_rules_to_symbol(event.symbol, event.owner)

    async def on_entry_removed(self, event: WatchlistEntryRemoved) -> None:
        self._market_data.unregister_symbol(event.symbol)
        self._alert_adapter.remove_rules_from_symbol(event.symbol, event.owner)
