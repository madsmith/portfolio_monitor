from dataclasses import dataclass
from typing import Any

from portfolio_monitor.service.types import AssetSymbol


@dataclass
class WatchlistEntryAdded:
    """Fired when an entry is added to a watchlist."""

    symbol: AssetSymbol
    alert_config: dict[str, Any]  # kind → args (may be empty)
    owner: str  # watchlist owner username


@dataclass
class WatchlistEntryRemoved:
    """Fired when an entry is removed from a watchlist."""

    symbol: AssetSymbol
    owner: str


@dataclass
class WatchlistEntryAlertsUpdated:
    """Fired when the alert config for a watchlist entry is replaced."""

    symbol: AssetSymbol
    old_alert_config: dict[str, Any]
    new_alert_config: dict[str, Any]
    owner: str
