from dataclasses import dataclass

from portfolio_monitor.data.aggregate_cache import Aggregate
from portfolio_monitor.service.types import AssetSymbol


@dataclass
class AggregateUpdated:
    """A new price bar arrived for a symbol."""

    symbol: AssetSymbol
    aggregate: Aggregate
