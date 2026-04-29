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
