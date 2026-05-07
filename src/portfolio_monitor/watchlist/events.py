from dataclasses import dataclass

from portfolio_monitor.service.types import AssetSymbol


@dataclass
class WatchlistEntryAdded:
    """Fired when an entry is added to a watchlist."""

    symbol: AssetSymbol
    owner: str


@dataclass
class WatchlistEntryRemoved:
    """Fired when an entry is removed from a watchlist."""

    symbol: AssetSymbol
    owner: str
