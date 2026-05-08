from dataclasses import dataclass

from portfolio_monitor.core import Currency
from portfolio_monitor.service.types import AssetSymbol


@dataclass
class PriceUpdated:
    """An asset's price changed."""

    symbol: AssetSymbol
    price: Currency


@dataclass
class PortfolioUpdated:
    """A portfolio's valuations were recalculated."""

    portfolio_name: str


@dataclass
class AssetAdded:
    """A new asset (ticker) was added to a portfolio."""

    symbol: AssetSymbol


@dataclass
class AssetRemoved:
    """An asset was fully removed from a portfolio (no lots remaining)."""

    symbol: AssetSymbol
